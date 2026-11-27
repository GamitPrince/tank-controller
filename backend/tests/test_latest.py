"""The latest-values endpoint and its liveness flags, on a fixed clock (S-084, P1-19).

Every name is made up. Example Co (7) has tank 71 and Sample Ltd (8) tank 81.
DEV-A is on tank 71 from CLAIMED and is still there; DEV-B is known, never claimed.
"""

from collections.abc import Callable, Iterator

import access_tokens
import cbor2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from tankapi import auth, liveness, session
from tankapi.db import AssignmentRow, AuditRow, CustomerRow, DeviceRow, PlantRow, TankRow
from tankapi.ingest import Accepted, ingest_message
from tankapi.latest import LIVENESS_HELP
from tankapi.main import app
from tankapi.records import MAX_BATCH_RECORDS

EXAMPLE, SAMPLE = 7, 8
T = 1_763_683_200
CLAIMED = T - 100
RADAR, PT100_1, PT100_2, PT100_3, UPTIME = 1001, 2001, 2002, 2003, 9001
STAFF = {auth.GROUPS_CLAIM: ["service"], "sub": "staff-1"}
NOT_FOUND = {"detail": "not found"}


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as db:
        db.add_all(rows)
        db.commit()


def reading(signal: int, q: int = 0, val: int = 12_000) -> dict:
    return {"id": signal, "q": q, "age": 100} | ({} if q in (3, 4) else {"val": val})


def scan(seq: int, t: int | None, *readings: dict) -> dict:
    timed = {"tk": False} if t is None else {"tk": True, "t": t}
    header = {"v": 1, "dev": "DEV-A", "sl": 1, "boot": bytes(16), "seq": seq, "up": seq}
    return header | timed | {"r": list(readings)}


def ingest(engine: Engine, *records: dict) -> None:
    with Session(engine) as db:
        for i in range(0, len(records), MAX_BATCH_RECORDS):
            payload = cbor2.dumps(list(records[i : i + MAX_BATCH_RECORDS]))
            assert isinstance(ingest_message(db, "tank/DEV-A/records", payload), Accepted)


@pytest.fixture
def site(engine: Engine) -> Engine:
    add(engine, *(CustomerRow(id=c, name=f"Customer {c}") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(PlantRow(id=c, customer_id=c, name="Plant A") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(TankRow(id=n, plant_id=n // 10, name="Tank 1") for n in (71, 81)))
    add(engine, DeviceRow(device_id="DEV-A"), DeviceRow(device_id="DEV-B"))
    add(engine, AssignmentRow(device_id="DEV-A", tank_id=71, valid_from_unix_s=CLAIMED))
    return engine


@pytest.fixture
def serve(site: Engine) -> Iterator[Callable[[float], TestClient]]:
    def client_at(now: float) -> TestClient:
        app.dependency_overrides[session.get_engine] = lambda: site
        app.dependency_overrides[auth.get_settings] = access_tokens.settings
        app.dependency_overrides[liveness.server_now] = lambda: now
        app.dependency_overrides[liveness.get_stale_rules] = liveness.StaleRules
        return TestClient(app)

    yield client_at
    app.dependency_overrides.clear()


def customer(customer_id: int) -> dict[str, str]:
    claims = {auth.GROUPS_CLAIM: ["operator"], auth.CUSTOMER_CLAIM: str(customer_id)}
    return access_tokens.bearer(**claims)


def latest(client: TestClient, headers: dict | None = None, device: str = "DEV-A"):
    return client.get(
        f"/v1/devices/{device}/latest", headers=headers or access_tokens.bearer(**STAFF)
    )


def body(client: TestClient, headers: dict | None = None) -> dict:
    response = latest(client, headers)
    assert response.status_code == 200, response.text
    return response.json()


def values(data: dict) -> dict[int, tuple]:
    return {
        v["signal_id"]: (v["t"], v["quality"], v["value"], v["liveness"]) for v in data["values"]
    }


def test_fresh_values_are_live_and_keep_their_quality(site, serve) -> None:
    faults = (reading(PT100_1, q=3), reading(PT100_2, q=4), reading(PT100_3, q=2, val=21_000))
    ingest(site, scan(0, T - 50, reading(UPTIME, val=3600)), scan(1, T, reading(RADAR), *faults))
    data = body(serve(T + 1))
    assert (data["device"], data["last_t"], data["server_time"]) == ("live", T, T + 1)
    assert values(data) == {
        RADAR: (T, "good", 12_000, "live"),
        PT100_1: (T, "fault", None, "live"),
        PT100_2: (T, "unconfigured", None, "live"),
        PT100_3: (T, "out_of_range", 21_000, "live"),
        UPTIME: (T - 50, "good", 3600, "live"),
    }


@pytest.mark.parametrize(("now", "expected"), [(T + 15, "live"), (T + 15.5, "stale")])
def test_a_silent_device_turns_stale_after_15_s(site, serve, now: float, expected: str) -> None:
    ingest(site, scan(0, T - 1, reading(RADAR, val=1)), scan(1, T, reading(RADAR)))
    data = body(serve(now))
    assert (data["device"], values(data)) == (expected, {RADAR: (T, "good", 12_000, expected)})


def test_the_devices_own_stale_quality_is_stale(site, serve) -> None:
    ingest(site, scan(0, T, reading(RADAR, q=1)))
    data = body(serve(T))
    assert (data["device"], values(data)) == ("live", {RADAR: (T, "stale", 12_000, "stale")})


@pytest.mark.parametrize("headers", [None, customer(EXAMPLE)], ids=["service", "customer"])
def test_a_device_whose_clock_is_not_known_is_never_live(site, serve, headers) -> None:
    ingest(site, scan(0, None, reading(RADAR, val=1)))
    assert body(serve(T), headers) | {"server_time": 0} == {
        "device_id": "DEV-A",
        "server_time": 0,
        "device": "time-unknown",
        "last_t": None,
        "values": [],
    }
    ingest(site, scan(1, T, reading(RADAR)), scan(2, None, reading(RADAR, val=2)))
    data = body(serve(T + 1), headers)
    assert (data["device"], values(data)) == ("time-unknown", {RADAR: (T, "good", 12_000, "live")})


def test_a_customer_sees_a_device_only_while_it_is_on_their_tank(site, serve) -> None:
    ingest(site, scan(0, T, reading(RADAR)))
    client = serve(T + 1)
    assert latest(client, customer(EXAMPLE)).status_code == 200
    for headers, device in ((customer(SAMPLE), "DEV-A"), (None, "DEV-B"), (None, "DEV-NONE")):
        response = latest(client, headers, device)
        assert (response.status_code, response.json()) == (404, NOT_FOUND)
    with Session(site) as db:
        db.execute(update(AssignmentRow).values(valid_to_unix_s=T + 1))
        db.commit()
    response = latest(client, customer(EXAMPLE))
    assert (response.status_code, response.json()) == (404, NOT_FOUND)


def test_a_customer_sees_no_scan_from_before_their_claim(site, serve) -> None:
    ingest(site, scan(0, CLAIMED - 10, reading(UPTIME)))
    client = serve(CLAIMED + 6)
    data = body(client, customer(EXAMPLE))
    assert (data["device"], data["last_t"], data["values"]) == ("stale", None, [])
    ingest(site, scan(1, CLAIMED + 5, reading(RADAR)))
    assert set(values(body(client, customer(EXAMPLE)))) == {RADAR}
    assert set(values(body(client))) == {RADAR, UPTIME}


def test_service_requests_are_audited_and_customer_requests_are_not(site, serve) -> None:
    ingest(site, scan(0, T, reading(RADAR)))
    client = serve(T)
    body(client)
    body(client, customer(EXAMPLE))
    with Session(site) as db:
        [entry] = db.scalars(select(AuditRow))
        assert (entry.subject, entry.route, entry.device_id, entry.status) == (
            "staff-1",
            "/v1/devices/{device_id}/latest",
            "DEV-A",
            200,
        )


def test_the_openapi_document_describes_the_liveness_field(serve) -> None:
    schema = serve(T).get("/openapi.json").json()
    assert list(schema["paths"]["/v1/devices/{device_id}/latest"]) == ["get"]
    schemas = schema["components"]["schemas"]
    assert schemas["Liveness"]["enum"] == ["live", "stale", "time-unknown"]
    field = schemas["LatestValue"]["properties"]["liveness"]
    assert field["description"] == LIVENESS_HELP
    assert {"liveness", "quality", "age_ms"} <= set(schemas["LatestValue"]["required"])
