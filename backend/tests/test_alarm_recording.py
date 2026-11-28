"""Advisory alarms recorded from newly stored scans, in the ingest transaction (S-090).

TEST DATA ONLY. Every customer, tank, device, threshold and reading here is made up.
"""

import logging

import cbor2
import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session
from test_alarm_thresholds import SET, add, threshold
from test_level_config import POINTS, chained, config

from tankapi import ingest
from tankapi.db import (
    AlarmEventRow,
    AlarmThresholdRow,
    AssignmentRow,
    CustomerRow,
    DeviceRow,
    PlantRow,
    ScanRow,
    TankRow,
)
from tankapi.ingest import Accepted, ingest_message

pytestmark = pytest.mark.postgres

# The server clock a day after the scans: a replayed backlog, judged at its own time.
NOW = SET + 86_400
TOPIC = "tank/DEV-A/records"
BOOT = bytes(16)
RADAR, UPPER_A = 1001, 2001


def scan(seq: int, value: int | None, t: int | None = None, q: int = 0, age: int = 100) -> dict:
    """Scan ``seq`` of DEV-A at ``SET + seq`` with one radar reading (none if ``value`` is None
    and ``q`` good); ``t`` overrides the time, and -1 makes it untimed."""
    readings = [] if value is None and q == 0 else [{"id": RADAR, "q": q, "age": age}]
    if value is not None:
        readings[0]["val"] = value
    t = SET + seq if t is None else t
    record = {"v": 1, "dev": "DEV-A", "sl": 1, "boot": BOOT, "seq": seq, "up": seq * 1000}
    record |= {"tk": t >= 0, "r": readings or [{"id": UPPER_A, "q": 0, "age": 1, "val": 0}]}
    return record | ({"t": t} if t >= 0 else {})


def send(engine: Engine, *scans: dict) -> Accepted:
    with Session(engine) as session:
        return ingest_message(session, TOPIC, cbor2.dumps(list(scans)), clock=lambda: NOW)


def events(engine: Engine) -> list[tuple]:
    columns = (AlarmEventRow.state, AlarmEventRow.reason, AlarmEventRow.unix_time_s)
    with Session(engine) as session:
        return session.execute(select(*columns).order_by(AlarmEventRow.id)).all()


@pytest.fixture
def site(engine: Engine) -> Engine:
    """DEV-A on Tank 1 from SET, with a warning high of 18 mA and a 0.5 mA deadband."""
    add(engine, CustomerRow(id=1, name="Example Co"), DeviceRow(device_id="DEV-A"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"))
    add(engine, AssignmentRow(device_id="DEV-A", tank_id=1, valid_from_unix_s=SET))
    add(engine, threshold(1, deadband=500))
    return engine


def test_an_alarm_is_raised_once_and_cleared_past_its_deadband(site: Engine) -> None:
    values = (17_900, 18_000, 18_100, 17_500, 17_499)
    assert send(site, *(scan(seq, value) for seq, value in enumerate(values))) == Accepted(5, 0)

    assert events(site) == [("high", None, SET + 1), ("normal", None, SET + 4)]
    with Session(site) as session:
        raised = session.scalars(select(AlarmEventRow)).first()
        copied = (raised.threshold_id, raised.value, raised.quality, raised.limit_value)
    assert copied + (raised.deadband,) == (1, 18_000.0, 0, 18_000, 500)


def test_a_redelivered_message_records_nothing_twice(site: Engine) -> None:
    send(site, scan(0, 18_100))
    assert send(site, scan(0, 18_100), scan(1, 18_200)) == Accepted(1, 1)
    assert events(site) == [("high", None, SET)]


def test_an_older_scan_stored_after_newer_ones_is_not_judged(site: Engine, caplog) -> None:
    send(site, scan(10, 17_000), scan(11, 17_100))
    caplog.set_level(logging.WARNING, logger="tankapi.alarm_events")

    assert send(site, scan(5, 18_500), scan(12, 18_200)) == Accepted(2, 0)

    assert events(site) == [("high", None, SET + 12)]
    assert "is older than one judged: not judged" in caplog.text


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (scan(1, None, q=3), "fault"),
        (scan(1, 18_100, q=1), "stale"),
        (scan(1, 18_100, age=2001), "stale"),  # older than two one-second periods
        (scan(1, None), "no_reading"),
        (scan(1, 18_100, t=-1), "time_unknown"),
        (scan(1, 18_100, t=NOW + 3), "time_unknown"),  # ahead of the server clock
    ],
)
def test_an_untrusted_value_neither_raises_nor_clears(site: Engine, bad: dict, reason: str) -> None:
    send(site, scan(0, 18_100), bad, scan(2, 17_600), scan(3, 17_400))

    t = None if bad.get("tk") is False else bad["t"]
    assert events(site) == [
        ("high", None, SET),
        ("cannot_evaluate", reason, t),
        ("high", None, SET + 2),  # inside the deadband: the alarm was never cleared
        ("normal", None, SET + 3),
    ]


def test_untrusted_values_from_the_start_raise_nothing(site: Engine) -> None:
    send(site, scan(0, None, q=3), scan(1, None, q=3), scan(2, 17_000))
    assert events(site) == [("cannot_evaluate", "fault", SET), ("normal", None, SET + 2)]


def test_a_changed_limit_judges_the_same_alarm_from_its_own_time(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(AlarmThresholdRow).values(valid_to_unix_s=SET + 2))
        session.commit()
    add(site, threshold(2, SET + 2, limit_value=19_000, deadband=500))

    send(site, scan(0, 18_500), scan(1, 18_600), scan(2, 18_600), scan(3, 18_400))

    with Session(site) as session:
        query = select(AlarmEventRow.state, AlarmEventRow.threshold_id, AlarmEventRow.limit_value)
        assert session.execute(query.order_by(AlarmEventRow.id)).all() == [
            ("high", 1, 18_000),
            ("normal", 2, 19_000),
        ]


def test_a_level_alarm_uses_the_tanks_level_configuration(site: Engine) -> None:
    add(site, config(1, 1, 1, SET), *chained(1, POINTS))
    add(site, threshold(2, measure="level_percent", limit_value=8_500, deadband=0))

    send(site, scan(0, 12_490), scan(1, 12_500), scan(2, 12_490), scan(3, 20_100, q=2))

    level, raw = (judged(site, threshold_id) for threshold_id in (2, 1))
    assert level == [
        ("high", None, pytest.approx(8_500)),  # 85 % in hundredths of a percent
        ("normal", None, pytest.approx(8_490)),
        ("cannot_evaluate", "out_of_range", None),
    ]
    assert raw == [("high", None, 20_100.0)]  # the raw limit still sees an overfill


def judged(engine: Engine, threshold_id: int) -> list[tuple]:
    query = select(AlarmEventRow.state, AlarmEventRow.reason, AlarmEventRow.value)
    with Session(engine) as session:
        rows = query.where(AlarmEventRow.threshold_id == threshold_id).order_by(AlarmEventRow.id)
        return session.execute(rows).all()


def test_a_level_alarm_on_an_unconfigured_tank_cannot_be_evaluated(site: Engine) -> None:
    add(site, threshold(2, measure="level_percent", limit_value=8_500, deadband=0))
    send(site, scan(0, 12_500))
    assert ("cannot_evaluate", "unconfigured", SET) in events(site)


def test_a_device_on_no_tank_or_two_at_once_raises_nothing(site: Engine, caplog) -> None:
    send(site, scan(0, 18_100, t=SET - 1))
    add(site, TankRow(id=2, plant_id=1, name="Tank 2"))
    add(
        site,
        AssignmentRow(
            device_id="DEV-A", tank_id=2, valid_from_unix_s=SET - 10, valid_to_unix_s=SET + 5
        ),
    )

    assert send(site, scan(1, 18_100)) == Accepted(1, 0)
    assert events(site) == []
    assert "overlapping assignments" in caplog.text


def test_an_untimed_scan_with_no_judged_scan_before_it_records_nothing(site: Engine) -> None:
    send(site, scan(0, 18_100, t=-1))
    assert events(site) == []


def test_a_failed_judgement_stores_neither_the_scan_nor_an_alarm(site, monkeypatch) -> None:
    def broken(*_args, **_kwargs) -> None:
        raise RuntimeError("made-up failure")

    monkeypatch.setattr(ingest, "record_alarm_events", broken)
    with pytest.raises(RuntimeError, match="made-up failure"):
        send(site, scan(0, 18_100))

    with Session(site) as session:
        assert session.scalar(select(func.count()).select_from(ScanRow)) == 0
    assert events(site) == []


def test_a_broken_level_configuration_cannot_be_evaluated(site: Engine, caplog) -> None:
    add(site, config(1, 1, 1, SET, max_height_mm=1_000.0), *chained(1, POINTS))  # points too high
    add(site, threshold(2, measure="level_percent", limit_value=8_500, deadband=0))

    send(site, scan(0, 12_500))

    assert judged(site, 2) == [("cannot_evaluate", "unconfigured", None)]
    assert "level refused for device DEV-A" in caplog.text


def test_overlapping_thresholds_of_one_kind_judge_nothing(site: Engine, caplog) -> None:
    with Session(site) as session:
        session.execute(update(AlarmThresholdRow).values(valid_to_unix_s=SET + 60))
        session.commit()
    add(site, threshold(2, SET + 1))

    assert send(site, scan(0, 18_100), scan(1, 18_100)) == Accepted(2, 0)
    assert events(site) == [("high", None, SET)]
    assert "tank 1 has overlapping thresholds" in caplog.text
