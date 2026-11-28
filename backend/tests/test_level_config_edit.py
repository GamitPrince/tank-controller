"""Setting a tank's level configuration (S-103, P1-04).

TEST DATA ONLY. Every customer, tank, person and number here is made up.
Example Co (7) has tank 71 with configuration version 1; Sample Ltd (8) has tank 81 with none.
"""

import json
from collections.abc import Iterator

import access_tokens
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_alarm_history import EXAMPLE, SAMPLE, STAFF, T
from test_level_config import POINTS, RANGE, at, chained, config
from test_threshold_edit import ADMIN, add, changes, person

from tankapi import auth, level_config_edit, session
from tankapi.db import AuditRow, CustomerRow, LevelConfigRow, PlantRow, TankRow
from tankapi.main import app

pytestmark = pytest.mark.postgres

ROUTE = "/v1/tanks/{tank_id}/level-configuration"
NOW = T + 50
NEW_POINTS = [[0.0, 0.0], [1000.0, 1500.0], [2000.0, 3600.0]]
BODY = (
    {"calculation_version": 1}
    | RANGE
    | {"points": [{"height_mm": h, "volume_l": v} for h, v in NEW_POINTS]}
)


@pytest.fixture
def site(engine: Engine) -> Engine:
    add(engine, *(CustomerRow(id=c, name=f"Customer {c}") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(PlantRow(id=c, customer_id=c, name="Plant A") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(TankRow(id=n, plant_id=n // 10, name="Tank 1") for n in (71, 81)))
    add(engine, config(1, 71, 1, T - 100))
    add(engine, *chained(1, POINTS))
    return engine


@pytest.fixture
def client(site: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(level_config_edit, "now_ms", lambda: NOW * 1_000 + 250)
    app.dependency_overrides[session.get_engine] = lambda: site
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def put(client: TestClient, tank_id: object = 71, headers: dict = ADMIN, **changes_):
    return client.put(ROUTE.format(tank_id=tank_id), json=BODY | changes_, headers=headers)


def configs(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        rows = db.scalars(select(LevelConfigRow).order_by(LevelConfigRow.id))
        return [(r.id, r.version, r.valid_from_unix_s, r.valid_to_unix_s) for r in rows]


def test_an_admin_replaces_the_configuration_from_the_server_second(site, client) -> None:
    response = put(client)

    assert response.status_code == 200, response.text
    assert response.json() == BODY | {"id": 2, "version": 2, "valid_from": NOW, "replaced": 1}
    assert configs(site) == [(1, 1, T - 100, NOW), (2, 2, NOW, None)]
    [change] = changes(site)
    kept = (change.subject, change.role, change.tank_id, change.kind, change.at_unix_ms)
    assert kept == ("admin-1", "admin", 71, "level_configuration", NOW * 1_000 + 250)
    assert (change.before_row_id, change.after_row_id) == (1, 2)
    numbers = {"calculation_version": 1} | RANGE
    assert json.loads(change.before) == numbers | {
        "version": 1,
        "points": [list(p) for p in POINTS],
        "valid_from": T - 100,
    }
    assert json.loads(change.after) == numbers | {
        "version": 2,
        "points": NEW_POINTS,
        "valid_from": NOW,
    }


def test_an_old_reading_keeps_the_configuration_of_its_time(site, client) -> None:
    assert put(client).status_code == 200
    assert at(site, 71, T + 10).table.version == 1
    new = at(site, 71, NOW + 10).table
    assert (new.version, [(p.height_mm, p.volume_l) for p in new.points]) == (
        2,
        [tuple(p) for p in NEW_POINTS],
    )


def test_a_first_configuration_has_no_before_and_version_one(site, client) -> None:
    response = put(client, tank_id=81, headers=STAFF)
    assert response.json()["version"] == 1 and response.json()["replaced"] is None
    [change] = changes(site)
    assert (change.role, change.tank_id, change.before, change.after_row_id) == (
        "service",
        81,
        None,
        2,
    )
    with Session(site) as db:
        entry = db.scalars(select(AuditRow)).one()
    assert (entry.method, entry.route, entry.status) == ("PUT", ROUTE, 200)


@pytest.mark.parametrize("role", ["operator", "maintenance"])
def test_operator_and_maintenance_are_refused(site, client, role) -> None:
    response = put(client, headers=person(role))
    assert (response.status_code, response.json()) == (403, {"detail": "not allowed"})
    assert len(configs(site)) == 1 and changes(site) == []


@pytest.mark.parametrize(("tank", "headers"), [(81, ADMIN), (99, ADMIN), (99, STAFF)])
def test_another_customers_tank_answers_as_an_unknown_one(site, client, tank, headers) -> None:
    response = put(client, tank_id=tank, headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "not found"})
    assert changes(site) == []


def points(*pairs) -> list[dict]:
    return [{"height_mm": h, "volume_l": v} for h, v in pairs]


@pytest.mark.parametrize(
    "changes_",
    [
        {"calculation_version": 2},
        {"range_high_mm": 0.0},  # the range must rise
        {"range_low_mm": -1.0},
        {"max_height_mm": 1e10},  # above the ceiling
        {"points": points((0.0, 0.0))},  # one point
        {"points": points((0.0, 0.0), (500.0, 400.0), (400.0, 800.0))},  # height falls
        {"points": points((0.0, 0.0), (500.0, 400.0), (600.0, 400.0))},  # volume flat
        {"points": points((0.0, 0.0), (2500.0, 4000.0))},  # above the full height
        {"points": points(*((float(n), float(n)) for n in range(201)))},
        {"points": [{"height_mm": 0.0}]},
        {"range_low_mm": "low"},
        {"version": 7},  # the server chooses the version
    ],
)
def test_a_configuration_breaking_a_rule_is_refused(site, client, changes_) -> None:
    response = put(client, **changes_)
    assert response.status_code == 422, response.text
    assert len(configs(site)) == 1 and changes(site) == []


def test_a_second_change_in_one_second_is_refused(site, client) -> None:
    assert put(client).status_code == 200
    assert put(client).status_code == 409
    assert len(configs(site)) == 2 and len(changes(site)) == 1


def test_a_clash_with_a_stored_configuration_is_refused(site, client) -> None:
    add(site, config(2, 81, 1, NOW, NOW + 5))
    add(site, *chained(2, POINTS))
    assert put(client, tank_id=81, headers=STAFF).status_code == 409
    assert len(configs(site)) == 2 and changes(site) == []
