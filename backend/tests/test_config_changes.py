"""The append-only change log of a tank's settings (S-101).

TEST DATA ONLY. Every customer, tank, person and value here is made up.
"""

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_alarm_thresholds import add

from tankapi.db import ConfigChangeRow, CustomerRow, PlantRow, TankRow

pytestmark = pytest.mark.postgres

CREATED = {
    "at_unix_ms": 1,
    "subject": "admin-1",
    "role": "admin",
    "tank_id": 71,
    "kind": "alarm_threshold",
    "after_row_id": 1,
    "after": '{"limit": 12000}',
}


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Tank 71 of customer 7, with one threshold created on it."""
    # One add per table: the models have no relationships to order the inserts by.
    add(engine, CustomerRow(id=7, name="Example Co"))
    add(engine, PlantRow(id=7, customer_id=7, name="Plant A"))
    add(engine, TankRow(id=71, plant_id=7, name="Tank 1"))
    add(engine, ConfigChangeRow(**CREATED))
    return engine


def changes(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        rows = db.scalars(select(ConfigChangeRow).order_by(ConfigChangeRow.id)).all()
        return [(r.role, r.kind, r.before_row_id, r.after_row_id, r.after) for r in rows]


def test_a_replacement_and_a_removal_are_kept_with_both_values(site: Engine) -> None:
    replaced = {"before_row_id": 1, "before": '{"limit": 12000}', "after_row_id": 2}
    removed = {"before_row_id": 3, "before": "{}", "after_row_id": None, "after": None}
    add(site, ConfigChangeRow(**CREATED | replaced | {"role": "service"}))
    add(site, ConfigChangeRow(**CREATED | removed | {"kind": "level_configuration"}))
    assert changes(site) == [
        ("admin", "alarm_threshold", None, 1, '{"limit": 12000}'),
        ("service", "alarm_threshold", 1, 2, '{"limit": 12000}'),
        ("admin", "level_configuration", 3, None, None),
    ]


@pytest.mark.parametrize(
    "statement", ["UPDATE config_changes SET subject = 'changed'", "DELETE FROM config_changes"]
)
def test_a_change_is_never_rewritten_or_deleted(site: Engine, statement: str) -> None:
    with pytest.raises(DBAPIError, match="config_changes is append-only"), site.begin() as db:
        db.execute(text(statement))
    assert len(changes(site)) == 1


def test_postgres_refuses_truncate(site: Engine) -> None:
    if site.dialect.name != "postgresql":
        pytest.skip("TRUNCATE is a Postgres statement")
    with pytest.raises(DBAPIError, match="config_changes is append-only"), site.begin() as db:
        db.execute(text("TRUNCATE config_changes"))
    assert len(changes(site)) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"role": "operator"},
        {"role": "maintenance"},
        {"kind": "device_assignment"},
        {"subject": ""},
        {"at_unix_ms": -1},
        {"tank_id": 99},  # no such tank
        {"after_row_id": None, "after": None},  # changes nothing
        {"after_row_id": None},  # a value without its row
        {"before_row_id": 1},  # a row without its value
    ],
)
def test_a_bad_change_is_refused(site: Engine, fields: dict) -> None:
    with pytest.raises(IntegrityError):
        add(site, ConfigChangeRow(**CREATED | fields))
    assert len(changes(site)) == 1
