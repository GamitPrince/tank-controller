"""Judging one value against one advisory alarm threshold (S-088, P1-18).

TEST DATA ONLY. Every tank, reading and threshold here is made up.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from test_level_config import POINTS, add, chained, config

import tankapi
from tankapi.alarm_rules import (
    THRESHOLD_SIGNAL_IDS,
    AlarmClass,
    AlarmState,
    Direction,
    Evaluation,
    Measure,
    Sample,
    Threshold,
    Unavailable,
    evaluate,
    level_sample,
    reading_sample,
)
from tankapi.db import AssignmentRow, CustomerRow, DeviceRow, PlantRow, TankRow
from tankapi.liveness import Liveness, StaleRules
from tankapi.records import Quality, Reading
from tankapi.tank_level import LevelState, TankLevel, tank_level

SIGNAL_LIST = Path(__file__).parents[2] / "interfaces" / "signals-v1.yaml"
RADAR, UPPER_A = 1001, 2001
T = 1_795_000_000
HIGH = Threshold(Measure.SIGNAL, RADAR, Direction.HIGH, AlarmClass.WARNING, 12_000, 200)
LOW = Threshold(Measure.SIGNAL, RADAR, Direction.LOW, AlarmClass.CRITICAL, 4_500, 100)
LEVEL_HIGH = Threshold(Measure.LEVEL_PERCENT, RADAR, Direction.HIGH, AlarmClass.ADVISORY, 8_500, 50)
LIVE = Liveness.LIVE
CANNOT = AlarmState.CANNOT_EVALUATE


def reading(value: int | None, quality: Quality = Quality.GOOD, signal: int = RADAR) -> Reading:
    return Reading(signal_id=signal, quality=quality, age_ms=100, value=value)


def judge(rule: Threshold, value: int, active: bool = False) -> AlarmState:
    return evaluate(rule, reading_sample(RADAR, reading(value), LIVE), active).state


def test_only_the_signal_lists_measurements_take_a_threshold() -> None:
    pieces = re.split(r"^\s*- id:\s*(\d+)\s*$", SIGNAL_LIST.read_text(), flags=re.MULTILINE)
    measured = {
        int(signal)
        for signal, body in zip(pieces[1::2], pieces[2::2], strict=True)
        if re.search(r"^\s+class:\s*measurement\s*$", body, re.MULTILINE)
    }
    assert measured == THRESHOLD_SIGNAL_IDS


@pytest.mark.parametrize(
    ("value", "active", "expected"),
    [
        (11_999, False, AlarmState.NORMAL),
        (12_000, False, AlarmState.HIGH),
        (12_001, False, AlarmState.HIGH),
        (11_900, False, AlarmState.NORMAL),  # in the deadband, not yet raised
        (11_999, True, AlarmState.HIGH),  # in the deadband, still raised
        (11_800, True, AlarmState.HIGH),  # at the clearing point
        (11_799, True, AlarmState.NORMAL),
    ],
)
def test_a_high_threshold_is_reached_at_its_limit_and_clears_below_the_deadband(
    value: int, active: bool, expected: AlarmState
) -> None:
    assert judge(HIGH, value, active) is expected


@pytest.mark.parametrize(
    ("value", "active", "expected"),
    [
        (4_501, False, AlarmState.NORMAL),
        (4_500, False, AlarmState.LOW),
        (4_499, False, AlarmState.LOW),
        (4_550, False, AlarmState.NORMAL),
        (4_600, True, AlarmState.LOW),
        (4_601, True, AlarmState.NORMAL),
    ],
)
def test_a_low_threshold_is_the_mirror_image(value: int, active: bool, expected: AlarmState):
    assert judge(LOW, value, active) is expected


def test_with_no_deadband_a_raised_alarm_clears_just_below_the_limit() -> None:
    tight = Threshold(Measure.SIGNAL, RADAR, Direction.HIGH, AlarmClass.WARNING, 12_000, 0)
    assert judge(tight, 12_000, active=True) is AlarmState.HIGH
    assert judge(tight, 11_999, active=True) is AlarmState.NORMAL


def test_a_value_hovering_at_the_limit_raises_once_and_clears_once() -> None:
    active, changes = False, []
    for value in (11_990, 12_000, 11_990, 12_010, 11_950, 11_850, 11_800, 11_799, 11_850):
        now_active = judge(HIGH, value, active) is AlarmState.HIGH
        if now_active != active:
            changes.append((value, now_active))
        active = now_active
    assert changes == [(12_000, True), (11_799, False)]


@pytest.mark.parametrize(
    ("quality", "reason"),
    [
        (Quality.FAULT, Unavailable.FAULT),
        (Quality.UNCONFIGURED, Unavailable.UNCONFIGURED),
        (Quality.STALE, Unavailable.STALE),
    ],
)
@pytest.mark.parametrize("active", [False, True])
def test_a_reading_that_cannot_be_trusted_never_raises_or_clears(
    quality: Quality, reason: Unavailable, active: bool
) -> None:
    value = 13_000 if quality is Quality.STALE else None
    sample = reading_sample(RADAR, reading(value, quality), LIVE)
    assert evaluate(HIGH, sample, active) == Evaluation(CANNOT, reason)


@pytest.mark.parametrize(
    ("liveness", "reason"),
    [(Liveness.STALE, Unavailable.STALE), (Liveness.TIME_UNKNOWN, Unavailable.TIME_UNKNOWN)],
)
def test_a_stale_or_untimed_good_value_cannot_be_evaluated(
    liveness: Liveness, reason: Unavailable
) -> None:
    sample = reading_sample(RADAR, reading(13_000), liveness)
    assert evaluate(HIGH, sample, active=False) == Evaluation(CANNOT, reason)
    assert evaluate(HIGH, sample, active=True) == Evaluation(CANNOT, reason)


def test_no_reading_cannot_be_evaluated() -> None:
    sample = reading_sample(RADAR, None, LIVE)
    assert evaluate(HIGH, sample, active=True) == Evaluation(CANNOT, Unavailable.NO_READING)


def test_an_out_of_range_reading_is_judged_as_measured() -> None:
    over = reading_sample(RADAR, reading(20_500, Quality.OUT_OF_RANGE), LIVE)
    under = reading_sample(RADAR, reading(3_500, Quality.OUT_OF_RANGE), LIVE)
    assert evaluate(HIGH, over, active=False) == Evaluation(AlarmState.HIGH)
    assert evaluate(LOW, under, active=False) == Evaluation(AlarmState.LOW)


@pytest.mark.parametrize(
    ("percent", "active", "expected"),
    [
        (84.75, False, AlarmState.NORMAL),
        (85.0, False, AlarmState.HIGH),
        (85.25, False, AlarmState.HIGH),
        (84.5, True, AlarmState.HIGH),  # 8450: the clearing point
        (84.25, True, AlarmState.NORMAL),
    ],
)
def test_a_level_threshold_is_in_hundredths_of_a_percent(
    percent: float, active: bool, expected: AlarmState
) -> None:
    level = TankLevel(status=LevelState.OK, t=T, level_percent=percent)
    assert evaluate(LEVEL_HIGH, level_sample(level), active).state is expected


@pytest.mark.parametrize("state", [s for s in LevelState if s is not LevelState.OK])
def test_a_level_without_figures_cannot_be_evaluated(state: LevelState) -> None:
    sample = level_sample(TankLevel(status=state))
    assert evaluate(LEVEL_HIGH, sample, active=True) == Evaluation(CANNOT, Unavailable(state.value))


@pytest.fixture
def tank(engine: Engine) -> Engine:
    """DEV-A on Example Co's Tank 1, configured: 0 mm at 4 mA, 3200 mm at 20 mA, 2000 mm full."""
    add(engine, CustomerRow(id=1, name="Example Co"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"), DeviceRow(device_id="DEV-A"))
    add(engine, AssignmentRow(device_id="DEV-A", tank_id=1, valid_from_unix_s=T - 3600))
    add(engine, config(1, 1, 1, T - 3600))
    add(engine, *chained(1, POINTS))
    return engine


@pytest.mark.parametrize(
    ("microamps", "now", "expected"),
    [
        (12_500, T + 1, Evaluation(AlarmState.HIGH)),  # 1700 mm: 85 %
        (12_490, T + 1, Evaluation(AlarmState.NORMAL)),  # 1698 mm: 84.9 %
        (12_500, T + 60, Evaluation(CANNOT, Unavailable.STALE)),
        (20_500, T + 1, Evaluation(CANNOT, Unavailable.OUT_OF_RANGE)),
    ],
)
def test_a_level_alarm_uses_the_level_s_086_serves(
    tank: Engine, microamps: int, now: int, expected: Evaluation
) -> None:
    radar = reading(microamps, Quality.OUT_OF_RANGE if microamps > 20_000 else Quality.GOOD)
    with Session(tank) as session:
        level = tank_level(session, "DEV-A", (T, radar), now, StaleRules())
    assert evaluate(LEVEL_HIGH, level_sample(level), active=False) == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"limit": True},
        {"limit": 12.5},
        {"deadband": -1},
        {"signal_id": 3001},  # the high-high level switch: a device contact
        {"signal_id": 9001},
        {"measure": Measure.LEVEL_PERCENT, "signal_id": 1002, "limit": 8_000},
        {"measure": Measure.LEVEL_PERCENT, "limit": 10_001},
        {"measure": Measure.LEVEL_PERCENT, "limit": -1},
        {"measure": Measure.LEVEL_PERCENT, "limit": 8_000, "deadband": 10_001},
    ],
)
def test_a_threshold_breaking_the_rules_is_refused(fields: dict) -> None:
    rule = {
        "measure": Measure.SIGNAL,
        "signal_id": RADAR,
        "direction": Direction.HIGH,
        "alarm_class": AlarmClass.WARNING,
        "limit": 12_000,
        "deadband": 200,
    }
    with pytest.raises((TypeError, ValueError)):
        Threshold(**(rule | fields))


def test_a_sample_of_another_measure_or_signal_is_refused() -> None:
    with pytest.raises(ValueError, match="measure and signal"):
        evaluate(LEVEL_HIGH, reading_sample(RADAR, reading(12_000), LIVE), active=False)
    with pytest.raises(ValueError, match="measure and signal"):
        evaluate(HIGH, Sample(Measure.SIGNAL, UPPER_A, 12_000), active=False)
    with pytest.raises(ValueError, match="not 1001"):
        reading_sample(RADAR, reading(12_000, signal=UPPER_A), LIVE)
    with pytest.raises(TypeError, match="whole-number"):
        reading_sample(RADAR, reading(True), LIVE)


def test_no_backend_module_can_publish_to_a_device() -> None:
    client = re.compile(r"^\s*(import|from)\s+(paho|boto3|botocore|awscrt|awsiot)", re.MULTILINE)
    sources = Path(tankapi.__file__).parent.glob("*.py")
    assert [path.name for path in sources if client.search(path.read_text())] == []
