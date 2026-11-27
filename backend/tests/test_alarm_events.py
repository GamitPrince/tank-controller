"""The append-only alarm history and the thresholds in force at a time (S-089).

TEST DATA ONLY. Every customer, tank, scan and threshold here is made up.
"""

import pytest
from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from test_alarm_thresholds import CHANGED, RADAR, SET, UPPER_A, add, threshold

from tankapi.alarm_rules import AlarmClass, Direction, Measure, Threshold
from tankapi.db import AlarmEventRow, AlarmThresholdRow, CustomerRow, PlantRow, ScanRow, TankRow
from tankapi.thresholds import ThresholdError, ThresholdInForce, thresholds_at

RAISED = {"state": "high", "value": 18_100.0, "quality": 0}


def event(**fields) -> AlarmEventRow:
    """Threshold 1 raised by scan 1 at SET unless ``fields`` say otherwise."""
    values = {"threshold_id": 1, "scan_record_id": 1, "unix_time_s": SET}
    values |= RAISED | {"limit_value": 18_000, "deadband": 200}
    return AlarmEventRow(**(values | fields))


def scan(row_id: int, unix_time_s: int | None) -> ScanRow:
    return ScanRow(
        id=row_id,
        device_id="DEV-A",
        signal_list_version=1,
        boot_id=bytes(16),
        sequence=row_id,
        uptime_ms=row_id * 1000,
        time_known=unix_time_s is not None,
        unix_time_s=unix_time_s,
    )


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Tank 1 with a warning high on its radar from SET, and three scans, one untimed."""
    add(engine, CustomerRow(id=1, name="Example Co"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"), TankRow(id=2, plant_id=1, name="Tank 2"))
    add(engine, threshold(1), scan(1, SET), scan(2, None), scan(3, SET + 1))
    return engine


def events(engine: Engine) -> list[tuple]:
    with Session(engine) as session:
        query = select(AlarmEventRow.state, AlarmEventRow.reason, AlarmEventRow.unix_time_s)
        return session.execute(query.order_by(AlarmEventRow.id)).all()


def test_a_raise_and_its_clear_are_two_rows(site: Engine) -> None:
    add(site, event(), event(scan_record_id=2, unix_time_s=None, **_unknown("time_unknown")))
    add(site, event(state="normal", value=17_700.0, scan_record_id=3, unix_time_s=SET + 1))
    assert events(site) == [
        ("high", None, SET),
        ("cannot_evaluate", "time_unknown", None),
        ("normal", None, SET + 1),
    ]


def _unknown(reason: str) -> dict:
    return {"state": "cannot_evaluate", "reason": reason, "value": None}


@pytest.mark.parametrize(
    "statement", ["UPDATE alarm_events SET state = 'normal'", "DELETE FROM alarm_events"]
)
def test_an_event_is_never_changed_or_deleted(site: Engine, statement: str) -> None:
    add(site, event())

    with pytest.raises(DBAPIError, match="alarm_events is append-only"), site.begin() as db:
        db.execute(text(statement))

    assert events(site) == [("high", None, SET)]


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"state": "raised"}, "state_known"),
        (_unknown("late"), "reason_known"),
        ({"state": "cannot_evaluate"}, "judged_or_reason"),
        ({"reason": "fault"}, "judged_or_reason"),
        ({"value": None}, "judged_or_reason"),
        (_unknown("fault") | {"value": 1.0}, "judged_or_reason"),
        ({"quality": 5}, "quality_known"),
        ({"quality": None}, "quality_unless_no_reading"),
        ({"unix_time_s": None}, "untimed_time_unknown"),
        (_unknown("fault") | {"unix_time_s": None}, "untimed_time_unknown"),
        ({"unix_time_s": -1}, "time_uint"),
        ({"deadband": -1}, "deadband_uint"),
    ],
)
def test_the_database_refuses_an_event_that_breaks_a_rule(
    site: Engine, fields: dict, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        add(site, event(**fields))


def test_a_missing_reading_has_no_quality(site: Engine) -> None:
    add(site, event(quality=None, **_unknown("no_reading")))
    assert events(site) == [("cannot_evaluate", "no_reading", SET)]


@pytest.mark.parametrize(
    "fields", [{"threshold_id": 9}, {"scan_record_id": 9}, {"limit_value": None}]
)
def test_an_event_needs_its_threshold_scan_and_limit(site: Engine, fields: dict) -> None:
    with pytest.raises(IntegrityError):
        add(site, event(**fields))


def test_one_scan_is_judged_once_against_one_threshold(site: Engine) -> None:
    add(site, event())
    with pytest.raises(IntegrityError, match="UNIQUE"):
        add(site, event(state="normal"))


def test_the_thresholds_in_force_are_those_of_the_scans_time(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(AlarmThresholdRow).values(valid_to_unix_s=CHANGED))
        session.commit()
    add(site, threshold(2, CHANGED, limit_value=17_500), threshold(3, signal_id=UPPER_A))
    add(site, threshold(4, tank_id=2), threshold(5, CHANGED + 60, alarm_class="critical"))

    with Session(site) as session:
        before, at_change = (thresholds_at(session, 1, t) for t in (CHANGED - 1, CHANGED))
        assert thresholds_at(session, 1, SET - 1) == []

    assert [item.id for item in before] == [1, 3]
    assert [(item.id, item.threshold.limit) for item in at_change] == [(2, 17_500), (3, 18_000)]
    assert before[0].key == at_change[0].key == (1, "signal", RADAR, "high", "warning")
    assert before[0] == ThresholdInForce(
        1, 1, Threshold(Measure.SIGNAL, RADAR, Direction.HIGH, AlarmClass.WARNING, 18_000, 200)
    )


def test_two_thresholds_of_one_kind_in_force_at_once_are_refused(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(AlarmThresholdRow).values(valid_to_unix_s=CHANGED + 60))
        session.commit()
    add(site, threshold(2, CHANGED))

    with Session(site) as session:
        assert len(thresholds_at(session, 1, CHANGED - 1)) == 1
        with pytest.raises(ThresholdError, match="tank 1 has overlapping thresholds"):
            thresholds_at(session, 1, CHANGED)


@pytest.mark.parametrize("unix_time_s", [None, True, float(SET)])
def test_an_untimed_or_fractional_time_is_refused(site: Engine, unix_time_s: object) -> None:
    with Session(site) as session, pytest.raises(TypeError, match="whole Unix seconds"):
        thresholds_at(session, 1, unix_time_s)
