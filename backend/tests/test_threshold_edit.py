"""Setting a tank's advisory alarm thresholds (S-102, P1-18).

TEST DATA ONLY. Every customer, tank, device, person, threshold and reading here is made up.
Example Co (7) has tank 71 with a warning high of 18 mA on the radar; Sample Ltd (8) tank 81.
"""

import json
import time
from collections.abc import Iterator

import access_tokens
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_alarm_history import EXAMPLE, SAMPLE, STAFF, T
from test_alarm_recording import events, scan, send
from test_alarm_thresholds import add, threshold

from tankapi import auth, session, settings_edit, threshold_edit
from tankapi.db import (
    AlarmThresholdRow,
    AssignmentRow,
    AuditRow,
    ConfigChangeRow,
    CustomerRow,
    DeviceRow,
    PlantRow,
    TankRow,
)
from tankapi.main import app

pytestmark = pytest.mark.postgres

ROUTE = "/v1/tanks/{tank_id}/alarm-thresholds"
NOW = T + 50
BODY = {
    "measure": "signal",
    "signal_id": 1001,
    "direction": "high",
    "alarm_class": "warning",
    "limit": 19_000,
    "deadband": 200,
}
ADMIN = access_tokens.bearer(
    **{auth.GROUPS_CLAIM: ["admin"], auth.CUSTOMER_CLAIM: str(EXAMPLE), "sub": "admin-1"}
)


def person(role: str, customer_id: int = EXAMPLE) -> dict[str, str]:
    claims = {auth.GROUPS_CLAIM: [role], auth.CUSTOMER_CLAIM: str(customer_id)}
    return access_tokens.bearer(**claims)


@pytest.fixture
def site(engine: Engine) -> Engine:
    """DEV-A on tank 71 from T - 100, which has threshold 1 from then; tank 81 has none."""
    add(engine, *(CustomerRow(id=c, name=f"Customer {c}") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(PlantRow(id=c, customer_id=c, name="Plant A") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(TankRow(id=n, plant_id=n // 10, name="Tank 1") for n in (71, 81)))
    add(engine, DeviceRow(device_id="DEV-A"))
    add(engine, AssignmentRow(device_id="DEV-A", tank_id=71, valid_from_unix_s=T - 100))
    add(engine, threshold(1, start=T - 100, tank_id=71))
    return engine


@pytest.fixture
def client(site: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(threshold_edit, "now_ms", lambda: NOW * 1_000 + 250)
    app.dependency_overrides[session.get_engine] = lambda: site
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def put(client: TestClient, tank_id: object = 71, headers: dict = ADMIN, **changes):
    return client.put(ROUTE.format(tank_id=tank_id), json=BODY | changes, headers=headers)


def thresholds(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        rows = db.scalars(select(AlarmThresholdRow).order_by(AlarmThresholdRow.id))
        return [
            (r.id, r.direction, r.limit_value, r.valid_from_unix_s, r.valid_to_unix_s) for r in rows
        ]


def changes(engine: Engine) -> list[ConfigChangeRow]:
    with Session(engine) as db:
        return list(db.scalars(select(ConfigChangeRow).order_by(ConfigChangeRow.id)))


def test_an_admin_replaces_a_threshold_from_the_server_second(site, client) -> None:
    response = put(client)

    assert response.status_code == 200, response.text
    assert response.json() == BODY | {"id": 2, "valid_from": NOW, "replaced": 1}
    assert thresholds(site) == [(1, "high", 18_000, T - 100, NOW), (2, "high", 19_000, NOW, None)]
    [change] = changes(site)
    kept = (change.at_unix_ms, change.subject, change.role, change.tank_id, change.kind)
    assert kept == (NOW * 1_000 + 250, "admin-1", "admin", 71, "alarm_threshold")
    assert (change.before_row_id, change.after_row_id) == (1, 2)
    rule = {"measure": "signal", "signal_id": 1001, "direction": "high", "alarm_class": "warning"}
    assert json.loads(change.before) == rule | {
        "limit_value": 18_000,
        "deadband": 200,
        "valid_from": T - 100,
    }
    assert json.loads(change.after) == rule | {
        "limit_value": 19_000,
        "deadband": 200,
        "valid_from": NOW,
    }


def test_a_new_alarm_is_created_with_no_before(site, client) -> None:
    response = put(client, signal_id=1002, direction="low", limit=4_500)
    assert response.json()["replaced"] is None
    [change] = changes(site)
    assert (change.before_row_id, change.before, change.after_row_id) == (None, None, 2)
    assert thresholds(site)[0][-1] is None  # the radar's high is untouched


def test_an_old_scan_is_still_judged_by_the_threshold_of_its_time(site, client) -> None:
    assert put(client).status_code == 200
    # Arriving after the change: 18.5 mA at T + 10 is past the old 18 mA, not the new 19 mA.
    send(site, scan(1, 18_500, t=T + 10), scan(2, 18_500, t=NOW + 10))
    assert events(site) == [("high", None, T + 10), ("normal", None, NOW + 10)]
    assert thresholds(site)[1][-1] is None


def test_service_edits_any_tank_and_is_audited(site, client) -> None:
    assert put(client, tank_id=81, headers=STAFF).status_code == 200
    assert [(c.subject, c.role, c.tank_id) for c in changes(site)] == [("staff-1", "service", 81)]
    with Session(site) as db:
        entry = db.scalars(select(AuditRow)).one()
    assert (entry.method, entry.route, entry.status) == ("PUT", ROUTE, 200)
    assert json.loads(entry.query) == {"tank_id": "81"}


@pytest.mark.parametrize("role", ["operator", "maintenance"])
def test_operator_and_maintenance_are_refused(site, client, role) -> None:
    response = put(client, headers=person(role))
    assert (response.status_code, response.json()) == (403, {"detail": "not allowed"})
    assert len(thresholds(site)) == 1 and changes(site) == []


@pytest.mark.parametrize(("tank", "headers"), [(81, ADMIN), (99, ADMIN), (99, STAFF)])
def test_another_customers_tank_answers_as_an_unknown_one(site, client, tank, headers) -> None:
    response = put(client, tank_id=tank, headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "not found"})
    assert changes(site) == []


@pytest.mark.parametrize(
    "changes_",
    [
        {"signal_id": 3001},  # a digital contact takes no threshold
        {"measure": "level_percent", "signal_id": 2001},
        {"measure": "level_percent", "limit": 10_001},
        {"deadband": -1},
        {"limit": 3_999},
        {"limit": 20_001},
        {"signal_id": 2001, "limit": 20_001},
        {"deadband": 16_001},
        {"direction": "low", "limit": 18_000},  # not below the high in force
        {"measure": "volume"},
        {"limit": "high"},
        {"limit": 18.5},
        {"note": "extra"},
    ],
)
def test_a_threshold_breaking_a_rule_is_refused(site, client, changes_) -> None:
    response = put(client, **changes_)
    assert response.status_code == 422, response.text
    assert len(thresholds(site)) == 1 and changes(site) == []


def test_a_high_must_lie_above_the_low_in_force(site, client) -> None:
    add(site, threshold(2, start=T - 100, tank_id=71, direction="low", limit_value=6_000))
    assert put(client, limit=6_000).status_code == 422
    assert put(client, limit=6_001).status_code == 200


def test_the_valid_range_ends_are_accepted(site, client) -> None:
    assert put(client, limit=20_000).status_code == 200
    assert put(client, signal_id=2006, direction="low", limit=0).status_code == 200


def test_a_second_change_in_one_second_is_refused(site, client) -> None:
    assert put(client).status_code == 200
    response = put(client, limit=19_500)
    assert response.status_code == 409
    assert [row[2] for row in thresholds(site)] == [18_000, 19_000] and len(changes(site)) == 1


def test_a_clash_with_a_stored_row_is_refused_and_nothing_kept(site, client) -> None:
    # A closed row of this key starting at NOW: the new row would repeat its start.
    add(site, threshold(2, start=NOW, end=NOW + 5, tank_id=71, signal_id=1002))
    response = put(client, signal_id=1002)
    assert response.status_code == 409
    assert len(thresholds(site)) == 2 and changes(site) == []


def test_no_token_is_refused(client) -> None:
    assert client.put(ROUTE.format(tank_id=71), json=BODY).status_code == 401


def test_the_server_clock_is_unix_milliseconds() -> None:
    before = time.time_ns() // 1_000_000
    assert before <= settings_edit.now_ms() <= time.time_ns() // 1_000_000
