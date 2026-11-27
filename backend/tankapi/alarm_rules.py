"""Whether one value is beyond one advisory alarm threshold (S-088, P1-18).

These alarms are reports for people, never actions: nothing here, or anywhere
in the backend, writes to a device or to the hardwired safety chain (AGENTS.md
section 1). The device's own alarm and trip contacts are separate signals and
take no threshold.

A threshold is one limit, high or low, of one class, on a stored analogue
signal or on the level % S-086 computes. Its ``limit`` and ``deadband`` are
whole numbers in the measure's stored unit: the signal's transmitted unit
(``interfaces/signals-v1.yaml``), or hundredths of a percent.

A high threshold is reached at ``value >= limit``. Once reached it stays reached
while ``value >= limit - deadband``, so a value hovering at the limit does not
flap, and clears below that; a low threshold is the mirror image. Whether it was
reached before (``active``) comes from the caller, which keeps the alarm's
history (S-089).

A value that cannot be trusted gives ``cannot_evaluate`` with the reason: a
fault, an unconfigured channel, a stale or untimed reading, no reading, or a
level that S-086 could not compute. It never raises and never clears an alarm,
and it is never reported as normal (AGENTS.md section 7). An out-of-range raw
reading is judged as measured, because the device sends it unclamped (S-017)
``[Confirm]``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tankapi.level import RADAR_LEVEL_SIGNAL_ID
from tankapi.liveness import Liveness
from tankapi.records import Quality, Reading
from tankapi.tank_level import LevelState, TankLevel

# signals-v1.yaml: the radar and pressure loop currents and the six PT100s; a test
# checks this against the list. Digital contacts and health signals take none.
THRESHOLD_SIGNAL_IDS = frozenset({1001, 1002, 2001, 2002, 2003, 2004, 2005, 2006})
# Level % thresholds are stored in hundredths of a percent [Confirm].
LEVEL_UNITS_PER_PERCENT = 100
LEVEL_FULL = 100 * LEVEL_UNITS_PER_PERCENT


class Measure(str, Enum):
    """What a threshold is applied to."""

    SIGNAL = "signal"
    LEVEL_PERCENT = "level_percent"


class Direction(str, Enum):
    HIGH = "high"
    LOW = "low"


class AlarmClass(str, Enum):
    """P1-18's classes; the class says how urgent, never what the plant does."""

    CRITICAL = "critical"
    WARNING = "warning"
    ADVISORY = "advisory"


class AlarmState(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    LOW = "low"
    CANNOT_EVALUATE = "cannot_evaluate"


class Unavailable(str, Enum):
    """Why a value cannot be judged."""

    NO_READING = "no_reading"
    FAULT = "fault"
    UNCONFIGURED = "unconfigured"
    STALE = "stale"
    TIME_UNKNOWN = "time_unknown"
    OUT_OF_RANGE = "out_of_range"


_REACHED = {Direction.HIGH: AlarmState.HIGH, Direction.LOW: AlarmState.LOW}
_UNAVAILABLE_FOR_QUALITY = {
    Quality.FAULT: Unavailable.FAULT,
    Quality.UNCONFIGURED: Unavailable.UNCONFIGURED,
    Quality.STALE: Unavailable.STALE,
}
_UNAVAILABLE_FOR_LIVENESS = {
    Liveness.STALE: Unavailable.STALE,
    Liveness.TIME_UNKNOWN: Unavailable.TIME_UNKNOWN,
}


@dataclass(frozen=True)
class Threshold:
    """One limit; the same rules as migration 0006, so a refused row is refused here too."""

    measure: Measure
    signal_id: int
    direction: Direction
    alarm_class: AlarmClass
    limit: int
    deadband: int

    def __post_init__(self) -> None:
        for name in ("signal_id", "limit", "deadband"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a whole number in the stored unit")
        if self.signal_id not in THRESHOLD_SIGNAL_IDS:
            raise ValueError(f"signal {self.signal_id} takes no threshold")
        if self.deadband < 0:
            raise ValueError("deadband must not be negative")
        if self.measure is Measure.LEVEL_PERCENT:
            self._check_level()

    def _check_level(self) -> None:
        if self.signal_id != RADAR_LEVEL_SIGNAL_ID:
            raise ValueError("level % comes from the radar, signal 1001")
        if not 0 <= self.limit <= LEVEL_FULL or self.deadband > LEVEL_FULL:
            raise ValueError("a level % limit and deadband lie within 0 to 100 %")


@dataclass(frozen=True)
class Sample:
    """A value in the measure's stored unit, or ``None`` and the reason it cannot be judged."""

    measure: Measure
    signal_id: int
    value: int | float | None
    reason: Unavailable | None = None


@dataclass(frozen=True)
class Evaluation:
    state: AlarmState
    reason: Unavailable | None = None


def reading_sample(signal_id: int, reading: Reading | None, liveness: Liveness) -> Sample:
    """A stored reading of ``signal_id`` as a sample; ``liveness`` from ``tankapi.liveness``."""
    if reading is None:
        return Sample(Measure.SIGNAL, signal_id, None, Unavailable.NO_READING)
    if reading.signal_id != signal_id:
        raise ValueError(f"reading is of signal {reading.signal_id}, not {signal_id}")
    reason = _UNAVAILABLE_FOR_LIVENESS.get(liveness) or _UNAVAILABLE_FOR_QUALITY.get(
        reading.quality
    )
    if reason is not None:
        return Sample(Measure.SIGNAL, signal_id, None, reason)
    if isinstance(reading.value, bool) or not isinstance(reading.value, int):
        raise TypeError(f"signal {signal_id} carries no whole-number value")
    return Sample(Measure.SIGNAL, signal_id, reading.value)


def level_sample(level: TankLevel) -> Sample:
    """S-086's level as a sample in hundredths of a percent; only ``ok`` carries a value."""
    if level.status is not LevelState.OK:
        # Every other state of S-086 has a reason of the same name.
        reason = Unavailable(level.status.value)
        return Sample(Measure.LEVEL_PERCENT, RADAR_LEVEL_SIGNAL_ID, None, reason)
    value = float(level.level_percent) * LEVEL_UNITS_PER_PERCENT
    return Sample(Measure.LEVEL_PERCENT, RADAR_LEVEL_SIGNAL_ID, value)


def evaluate(threshold: Threshold, sample: Sample, active: bool) -> Evaluation:
    """The threshold's state for ``sample``, given whether its alarm is raised now."""
    if (sample.measure, sample.signal_id) != (threshold.measure, threshold.signal_id):
        raise ValueError("the sample is not of the threshold's measure and signal")
    if sample.value is None:
        return Evaluation(AlarmState.CANNOT_EVALUATE, sample.reason)
    if _beyond(threshold, sample.value, 0) or (
        active and _beyond(threshold, sample.value, threshold.deadband)
    ):
        return Evaluation(_REACHED[threshold.direction])
    return Evaluation(AlarmState.NORMAL)


def _beyond(threshold: Threshold, value: int | float, allowance: int) -> bool:
    """Whether ``value`` is at or past the limit, moved back by ``allowance``."""
    if threshold.direction is Direction.HIGH:
        return value >= threshold.limit - allowance
    return value <= threshold.limit + allowance
