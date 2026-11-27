from collections.abc import Iterator
from pathlib import Path

import access_tokens
import cbor2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, make_url
from sqlalchemy.orm import Session

from tankapi import auth, readings, session
from tankapi.ingest import Accepted, ingest_message
from tankapi.main import app

# The S-067 fixture: SIM-0001, seq 0 to 2 with no time, seq 3 and 4 at T + 3 and
# T + 4; 1001 out of range, 2001 faulted, 3001 a good bool.
PAYLOAD = bytes.fromhex(
    (Path(__file__).parent / "fixtures" / "simulator-batch-cbor-hex.txt").read_text()
)
TOPIC = "tank/SIM-0001/records"
BOOT = bytes.fromhex("047b10ac425bc442aff4f714e96f5c76")
T = 1_763_683_200
URL = "/v1/devices/SIM-0001/readings"


def ingest(engine: Engine, payload: bytes) -> None:
    with Session(engine) as db:
        assert isinstance(ingest_message(db, TOPIC, payload), Accepted)


def gap(seq: int, first_t: int | None, last_t: int | None) -> dict:
    def mark(offset: int, t: int | None) -> dict:
        tk = {"tk": False} if t is None else {"tk": True, "t": t}
        return {"boot": BOOT, "seq": seq + offset, "up": (seq + offset) * 1000, **tk}

    body = {"lost": 2, "first": mark(0, first_t), "last": mark(1, last_t)}
    return {"v": 1, "dev": "SIM-0001", "gap": body}


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    ingest(engine, PAYLOAD)
    app.dependency_overrides[session.get_engine] = lambda: engine
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app, headers=access_tokens.bearer())
    app.dependency_overrides.clear()


def query(client: TestClient, signal: int = 1001, start: int = T, end: int = T + 60) -> dict:
    response = client.get(URL, params={"signal": signal, "from": start, "to": end})
    assert response.status_code == 200, response.text
    return response.json()


def test_out_of_range_reading_comes_back_as_measured_with_quality_and_age(
    client: TestClient,
) -> None:
    body = query(client)

    assert (body["device_id"], body["signal_id"], body["from"], body["to"]) == (
        "SIM-0001",
        1001,
        T,
        T + 60,
    )
    assert body["points"][0] == {
        "t": T + 3,
        "boot_id": BOOT.hex(),
        "sequence": 3,
        "signal_list_version": 1,
        "quality": "out_of_range",
        "age_ms": 27,
        "value": 21600,
    }
    assert [p["t"] for p in body["points"]] == [T + 3, T + 4]
    assert body["gaps"] == []


def test_faulted_reading_has_no_value_and_a_bool_stays_a_bool(client: TestClient) -> None:
    faulted = query(client, signal=2001)["points"]
    contact = query(client, signal=3001)["points"]

    assert [(p["quality"], p["value"]) for p in faulted] == [("fault", None)] * 2
    assert [(p["quality"], p["value"]) for p in contact] == [("good", False)] * 2


def test_scans_with_unknown_time_are_left_out_and_counted(client: TestClient) -> None:
    body = query(client, start=0, end=3600)

    assert body["points"] == []
    assert body["untimed"] == {"points": 3, "gaps": 0}


def test_gaps_that_overlap_or_may_overlap_the_range_are_returned(
    client: TestClient, engine: Engine
) -> None:
    gaps = [gap(5, T + 5, T + 6), gap(7, None, T + 8), gap(9, None, None), gap(11, T + 99, None)]
    ingest(engine, cbor2.dumps([*gaps, gap(13, T - 9, T - 8)]))

    body = query(client)

    assert [(g["first"]["t"], g["last"]["t"]) for g in body["gaps"]] == [
        (T + 5, T + 6),
        (None, T + 8),
    ]
    assert body["gaps"][0] == {
        "lost": 2,
        "first": {"boot_id": BOOT.hex(), "sequence": 5, "t": T + 5},
        "last": {"boot_id": BOOT.hex(), "sequence": 6, "t": T + 6},
    }
    assert body["untimed"]["gaps"] == 1
    assert [p["t"] for p in body["points"]] == [T + 3, T + 4]


def test_empty_range_of_a_known_device_returns_no_points(client: TestClient) -> None:
    body = query(client, start=T + 5, end=T + 6)

    assert (body["points"], body["gaps"]) == ([], [])


def test_unknown_device_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/devices/SIM-9999/readings", params={"signal": 1, "from": 0, "to": 1})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"from": T, "to": T + 1},
        {"signal": 1001, "to": T + 1},
        {"signal": "x", "from": T, "to": T + 1},
        {"signal": -1, "from": T, "to": T + 1},
        {"signal": 1001, "from": -1, "to": T},
        {"signal": 1001, "from": T, "to": T},
        {"signal": 1001, "from": T + 1, "to": T},
        {"signal": 1001, "from": T, "to": T + readings.MAX_RANGE_S + 1},
    ],
)
def test_bad_parameters_are_refused(client: TestClient, params: dict) -> None:
    assert client.get(URL, params=params).status_code == 422


def test_device_id_over_64_characters_is_refused(client: TestClient) -> None:
    response = client.get(
        f"/v1/devices/{'D' * 65}/readings", params={"signal": 1, "from": 0, "to": 1}
    )

    assert response.status_code == 422


def test_more_points_than_the_limit_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(readings, "MAX_POINTS", 1)

    response = client.get(URL, params={"signal": 1001, "from": T, "to": T + 60})

    assert response.status_code == 422
    assert "narrow the range" in response.json()["detail"]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_are_not_allowed(client: TestClient, method: str) -> None:
    assert getattr(client, method)(URL).status_code == 405


def test_engine_comes_from_the_database_url_variable(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(session.DATABASE_URL_VARIABLE, raising=False)
    with pytest.raises(RuntimeError, match=session.DATABASE_URL_VARIABLE):
        session.get_engine()

    monkeypatch.setenv(session.DATABASE_URL_VARIABLE, database_url)
    engine = session.get_engine()
    try:
        assert engine.url == make_url(database_url)
        assert session.get_engine() is engine
    finally:
        engine.dispose()
        session._engine_for.cache_clear()
