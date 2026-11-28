"""The append-only table of alarm acknowledgements (S-092, P1-18).

TEST DATA ONLY. Every customer, tank, threshold, person and event here is made up.
"""

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_alarm_history import T, event, store
from test_alarm_thresholds import add, threshold

from tankapi.db import AlarmAcknowledgementRow, CustomerRow, PlantRow, TankRow

KEPT = {"alarm_event_id": 1, "subject": "user-1", "role": "operator", "at_unix_ms": 1}


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Tank 71 of customer 7, with raised events 1 and 2 and the first acknowledged."""
    # One add per table: the models have no relationships to order the inserts by.
    add(engine, CustomerRow(id=7, name="Example Co"))
    add(engine, PlantRow(id=7, customer_id=7, name="Plant A"))
    add(engine, TankRow(id=71, plant_id=7, name="Tank 1"))
    add(engine, threshold(1, start=T, tank_id=71))
    store(engine, *event(1, T + 10), *event(2, T + 20))
    add(engine, AlarmAcknowledgementRow(**KEPT, note="Seen."))
    return engine


def acknowledgements(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        rows = db.scalars(select(AlarmAcknowledgementRow)).all()
        return [
            (row.alarm_event_id, row.subject, row.role, row.at_unix_ms, row.note) for row in rows
        ]


def test_an_acknowledgement_is_kept_with_who_and_when(site: Engine) -> None:
    add(site, AlarmAcknowledgementRow(**KEPT | {"alarm_event_id": 2, "role": "admin"}))
    assert acknowledgements(site) == [
        (1, "user-1", "operator", 1, "Seen."),
        (2, "user-1", "admin", 1, None),
    ]


@pytest.mark.parametrize(
    "statement",
    ["UPDATE alarm_acknowledgements SET note = 'changed'", "DELETE FROM alarm_acknowledgements"],
)
def test_an_acknowledgement_is_never_changed_or_deleted(site: Engine, statement: str) -> None:
    refused = pytest.raises(DBAPIError, match="alarm_acknowledgements is append-only")
    with refused, site.begin() as db:
        db.execute(text(statement))
    assert acknowledgements(site) == [(1, "user-1", "operator", 1, "Seen.")]


@pytest.mark.parametrize(
    "fields",
    [
        {"alarm_event_id": 1},  # a second acknowledgement of one event
        {"alarm_event_id": 99},  # no such event
        {"role": "service"},
        {"subject": ""},
        {"note": ""},
        {"note": "x" * 201},
        {"at_unix_ms": -1},
    ],
)
def test_a_second_or_a_bad_row_is_refused(site: Engine, fields: dict) -> None:
    with pytest.raises(IntegrityError):
        add(site, AlarmAcknowledgementRow(**KEPT | {"alarm_event_id": 2} | fields))
    assert len(acknowledgements(site)) == 1
