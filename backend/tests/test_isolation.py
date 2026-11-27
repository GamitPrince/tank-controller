"""Each customer sees only its own share of a device's readings (S-078, P1-20).

Every name is made up. Example Co (7) has tanks 71 and 72, Sample Ltd (8) tank
81. DEV-A is claimed onto tank 71 and DEV-B onto tank 81 at T. DEV-C is known
but never claimed, and DEV-X has records but no device row. Each sent a scan
every 5 s from T - 10, so its first two scans are from before any claim.
"""

import logging
from collections.abc import Iterator

import access_tokens
import cbor2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from tankapi import auth, session
from tankapi.db import AssignmentRow, CustomerRow, DeviceRow, PlantRow, TankRow
from tankapi.ingest import Accepted, ingest_message
from tankapi.main import app
from tankapi.records import MAX_BATCH_RECORDS

EXAMPLE, SAMPLE, NOBODY = 7, 8, 9
BOOT = bytes(range(16))
SIGNAL = 1001
T = 1_763_683_200
MOVED = T + 30
SCAN_TIMES = [T - 10 + 5 * seq for seq in range(14)]
CLAIMED_TIMES = [t for t in SCAN_TIMES if t >= T]


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as db:
        db.add_all(rows)
        db.commit()


def assign(engine: Engine, device: str, tank: int, start: int, end: int | None = None) -> None:
    row = AssignmentRow(
        device_id=device, tank_id=tank, valid_from_unix_s=start, valid_to_unix_s=end
    )
    add(engine, row)


def move(engine: Engine, device: str, at: int, to_tank: int | None) -> None:
    """End the device's open assignment at ``at``, then open one on ``to_tank`` unless None."""
    is_open = AssignmentRow.valid_to_unix_s.is_(None)
    with Session(engine) as db:
        db.execute(
            update(AssignmentRow)
            .where(AssignmentRow.device_id == device, is_open)
            .values(valid_to_unix_s=at)
        )
        db.commit()
    if to_tank is not None:
        assign(engine, device, to_tank, at)


def mark(seq: int, t: int | None) -> dict:
    timed = {"tk": False} if t is None else {"tk": True, "t": t}
    return {"boot": BOOT, "seq": seq, "up": seq * 1000, **timed}


def scan(device: str, seq: int, t: int | None) -> dict:
    reading = {"id": SIGNAL, "q": 0, "age": 1, "val": seq}
    return {"v": 1, "dev": device, "sl": 1, **mark(seq, t), "r": [reading]}


def gap(device: str, seq: int, first_t: int | None, last_t: int | None) -> dict:
    return {
        "v": 1,
        "dev": device,
        "gap": {"lost": 2, "first": mark(seq, first_t), "last": mark(seq + 1, last_t)},
    }


def ingest(engine: Engine, device: str, records: list[dict]) -> None:
    with Session(engine) as db:
        for i in range(0, len(records), MAX_BATCH_RECORDS):
            payload = cbor2.dumps(records[i : i + MAX_BATCH_RECORDS])
            assert isinstance(ingest_message(db, f"tank/{device}/records", payload), Accepted)


@pytest.fixture
def site(engine: Engine) -> Engine:
    add(
        engine,
        CustomerRow(id=EXAMPLE, name="Example Co"),
        CustomerRow(id=SAMPLE, name="Sample Ltd"),
    )
    add(engine, *(PlantRow(id=c, customer_id=c, name="Plant A") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(TankRow(id=n, plant_id=n // 10, name=f"Tank {n % 10}") for n in (71, 72, 81)))
    add(engine, *(DeviceRow(device_id=device) for device in ("DEV-A", "DEV-B", "DEV-C")))
    for device in ("DEV-A", "DEV-B", "DEV-C", "DEV-X"):
        ingest(engine, device, [scan(device, seq, t) for seq, t in enumerate(SCAN_TIMES)])
    assign(engine, "DEV-A", 71, T)
    assign(engine, "DEV-B", 81, T)
    return engine


@pytest.fixture
def client(site: Engine) -> Iterator[TestClient]:
    app.dependency_overrides[session.get_engine] = lambda: site
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def customer(customer_id: int, role: str = "operator") -> dict[str, str]:
    return access_tokens.bearer(
        **{auth.GROUPS_CLAIM: [role], auth.CUSTOMER_CLAIM: str(customer_id)}
    )


def service() -> dict[str, str]:
    return access_tokens.bearer(**{auth.GROUPS_CLAIM: ["service"]})


def read(client: TestClient, device: str, headers: dict, start: int = T - 10, end: int = T + 60):
    params = {"signal": SIGNAL, "from": start, "to": end}
    return client.get(f"/v1/devices/{device}/readings", params=params, headers=headers)


def seen(client: TestClient, device: str, headers: dict, start: int = T - 10) -> list[int]:
    response = read(client, device, headers, start)
    assert response.status_code == 200, response.text
    return [point["t"] for point in response.json()["points"]]


@pytest.mark.parametrize("role", ["operator", "maintenance", "admin"])
def test_each_customer_sees_its_own_device_and_not_the_others(
    client: TestClient, role: str
) -> None:
    assert seen(client, "DEV-A", customer(EXAMPLE, role)) == CLAIMED_TIMES
    assert seen(client, "DEV-B", customer(SAMPLE, role)) == CLAIMED_TIMES
    assert read(client, "DEV-B", customer(EXAMPLE, role)).status_code == 404
    assert read(client, "DEV-A", customer(SAMPLE, role)).status_code == 404


def test_service_sees_every_device_with_every_record(client: TestClient, site: Engine) -> None:
    ingest(site, "DEV-C", [scan("DEV-C", 50, None)])
    for device in ("DEV-A", "DEV-B", "DEV-C", "DEV-X"):
        assert seen(client, device, service()) == SCAN_TIMES
    assert read(client, "DEV-C", service()).json()["untimed"] == {"points": 1, "gaps": 0}


@pytest.mark.parametrize(
    ("device", "end"),
    [("DEV-B", T + 60), ("DEV-C", T + 60), ("DEV-X", T + 60), ("DEV-A", T), ("DEV-Z", T + 60)],
    ids=["other customer's", "never claimed", "no device row", "before the claim", "unknown"],
)
def test_device_the_caller_may_not_see_answers_as_an_unknown_one(
    client: TestClient, device: str, end: int
) -> None:
    unknown = read(client, "DEV-Z", customer(EXAMPLE))
    response = read(client, device, customer(EXAMPLE), end=end)
    assert (response.status_code, response.json()) == (404, {"detail": "not found"})
    assert (response.content, dict(response.headers)) == (unknown.content, dict(unknown.headers))


def test_device_moved_to_another_customer_shows_each_its_own_part(
    client: TestClient, site: Engine
) -> None:
    move(site, "DEV-A", MOVED, to_tank=81)
    assert seen(client, "DEV-A", customer(EXAMPLE)) == [t for t in CLAIMED_TIMES if t < MOVED]
    assert seen(client, "DEV-A", customer(SAMPLE)) == [t for t in SCAN_TIMES if t >= MOVED]
    assert read(client, "DEV-A", customer(EXAMPLE), MOVED).status_code == 404


def test_readings_after_a_release_are_shown_to_nobody(client: TestClient, site: Engine) -> None:
    move(site, "DEV-A", MOVED, to_tank=None)
    assert seen(client, "DEV-A", customer(EXAMPLE)) == [t for t in CLAIMED_TIMES if t < MOVED]
    assert read(client, "DEV-A", customer(EXAMPLE), MOVED).status_code == 404
    assert seen(client, "DEV-A", service()) == SCAN_TIMES


def test_untimed_records_are_withheld_from_customers(client: TestClient, site: Engine) -> None:
    ingest(site, "DEV-A", [scan("DEV-A", 50, None), gap("DEV-A", 60, None, None)])
    body = read(client, "DEV-A", customer(EXAMPLE)).json()
    assert (body["untimed"], [p["t"] for p in body["points"]]) == (None, CLAIMED_TIMES)
    assert read(client, "DEV-A", service()).json()["untimed"] == {"points": 1, "gaps": 1}


def test_a_gap_is_shown_only_to_the_customer_it_lies_within(
    client: TestClient, site: Engine
) -> None:
    move(site, "DEV-A", MOVED, to_tank=81)
    gaps = [
        (T - 9, T - 8),
        (T + 1, T + 2),
        (MOVED - 1, MOVED + 1),
        (MOVED + 1, MOVED + 2),
        (None, T + 3),
    ]
    ingest(site, "DEV-A", [gap("DEV-A", 100 + 2 * i, *times) for i, times in enumerate(gaps)])

    def gaps_seen(headers: dict) -> list[tuple]:
        found = read(client, "DEV-A", headers).json()["gaps"]
        return [(g["first"]["t"], g["last"]["t"]) for g in found]

    assert gaps_seen(customer(EXAMPLE)) == [(T + 1, T + 2)]
    assert gaps_seen(customer(SAMPLE)) == [(MOVED + 1, MOVED + 2)]
    assert gaps_seen(service()) == gaps


def test_a_move_between_a_customers_own_tanks_hides_nothing(
    client: TestClient, site: Engine
) -> None:
    move(site, "DEV-A", MOVED, to_tank=72)
    ingest(site, "DEV-A", [gap("DEV-A", 100, MOVED - 1, MOVED + 1)])
    body = read(client, "DEV-A", customer(EXAMPLE)).json()
    assert ([p["t"] for p in body["points"]], len(body["gaps"])) == (CLAIMED_TIMES, 1)


def test_overlapping_assignments_refuse_the_request_with_a_fixed_body(
    client: TestClient, site: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="tankapi.readings")
    assign(site, "DEV-C", 71, T, MOVED + 10)
    assign(site, "DEV-C", 81, MOVED, T + 60)
    headers = customer(NOBODY)
    response = read(client, "DEV-C", headers)
    assert (response.status_code, response.json()) == (500, {"detail": "server error"})
    assert "DEV-C" in caplog.text
    assert headers["Authorization"].removeprefix("Bearer ") not in caplog.text
    assert seen(client, "DEV-C", service()) == SCAN_TIMES
