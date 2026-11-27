"""Level height, level % and volume from the radar loop current (S-082).

ADR-0004 decision 10 and its amendment 1 compute level % and volume in the
backend, not in the firmware, and there is no mass in Phase 1. The radar
transmitter (signal 1001) sends its loop current in microamps. The tank's
transducer range turns 4 to 20 mA into a level height, and the tank's
strapping table turns the height into a volume by linear interpolation between
its points. The table is always supplied as finished points, never generated
from dimensions here: a dished bottom and heating coils make the pilot tank's
bottom zone fit no formula (S-035).

A faulted, stale or out-of-range input gives an explicit status and no figures,
never a substitute, a clamp or an extrapolation (AGENTS.md section 7, S-035).
Pressure level (signal 1002) is not an input: comparing it with the radar is a
Phase 2 check.

Every result carries the strapping table's version and ``CALCULATION_VERSION``
(ADR-0007 decision 9), so a stored figure can be reproduced from the raw
archive. Storing tables, choosing the version in effect and storing results are
later stories.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise

from tankapi.records import Quality, Reading

RADAR_LEVEL_SIGNAL_ID = 1001
# signals-v1.yaml, signal 1001: sent in microamps, valid from 4.0 to 20.0 mA.
LOOP_LOW_UA = 4_000
LOOP_HIGH_UA = 20_000
# Interpolation needs two points. No higher count is required: S-035's 0.5% accuracy
# criterion against the tank's calibration chart proves a table (tech lead, 27 Nov 2026).
MIN_STRAPPING_POINTS = 2
PERCENT = 100.0

# Raise this whenever the method below changes, so old figures stay reproducible.
CALCULATION_VERSION = 1


class LevelStatus(Enum):
    """The result states S-035 resolved: only ``OK`` carries figures."""

    OK = "ok"
    FAULT = "fault"
    OUT_OF_RANGE = "out_of_range"
    STALE = "stale"


# Every reading quality except GOOD, and the status it gives.
_STATUS_FOR_QUALITY = {
    Quality.STALE: LevelStatus.STALE,
    Quality.OUT_OF_RANGE: LevelStatus.OUT_OF_RANGE,
    Quality.FAULT: LevelStatus.FAULT,
    Quality.UNCONFIGURED: LevelStatus.FAULT,
}


@dataclass(frozen=True)
class StrappingPoint:
    height_mm: float
    volume_l: float


@dataclass(frozen=True)
class StrappingTable:
    """One version of one tank's transducer range and strapping table (S-035).

    ``range_low_mm`` is the level at 4 mA and ``range_high_mm`` the level at
    20 mA. The points rise in both height and volume and end at or below
    ``max_height_mm``, the tank's full height. A table that breaks any of this
    is refused when it is made, so no calculation runs on it.
    """

    version: int
    range_low_mm: float
    range_high_mm: float
    max_height_mm: float
    points: tuple[StrappingPoint, ...]

    def __post_init__(self) -> None:
        _check_table(self)


@dataclass(frozen=True)
class LevelResult:
    """The figures are ``None`` exactly when ``status`` is not ``OK``."""

    status: LevelStatus
    level_mm: float | None
    level_percent: float | None
    volume_l: float | None
    table_version: int
    calculation_version: int = CALCULATION_VERSION


def compute_level(reading: Reading, table: StrappingTable) -> LevelResult:
    """Level height, level % (of ``max_height_mm``) and volume for one radar reading."""
    if reading.signal_id != RADAR_LEVEL_SIGNAL_ID:
        raise ValueError(f"signal {reading.signal_id} is not the radar level")
    if reading.quality in _STATUS_FOR_QUALITY:
        return _without_figures(_STATUS_FOR_QUALITY[reading.quality], table)
    current_ua = reading.value
    if isinstance(current_ua, bool) or not isinstance(current_ua, int):
        return _without_figures(LevelStatus.FAULT, table)
    if not LOOP_LOW_UA <= current_ua <= LOOP_HIGH_UA:
        return _without_figures(LevelStatus.OUT_OF_RANGE, table)
    level_mm = _level_mm(current_ua, table)
    volume_l = _volume_l(level_mm, table.points)
    if volume_l is None:
        return _without_figures(LevelStatus.OUT_OF_RANGE, table)
    level_percent = PERCENT * level_mm / table.max_height_mm
    return LevelResult(LevelStatus.OK, level_mm, level_percent, volume_l, table.version)


def _without_figures(status: LevelStatus, table: StrappingTable) -> LevelResult:
    return LevelResult(status, None, None, None, table.version)


def _level_mm(current_ua: int, table: StrappingTable) -> float:
    span_mm = table.range_high_mm - table.range_low_mm
    fraction = (current_ua - LOOP_LOW_UA) / (LOOP_HIGH_UA - LOOP_LOW_UA)
    return table.range_low_mm + fraction * span_mm


def _volume_l(level_mm: float, points: tuple[StrappingPoint, ...]) -> float | None:
    """Linear interpolation between the bracketing points; ``None`` outside the table."""
    if not points[0].height_mm <= level_mm <= points[-1].height_mm:
        return None
    upper = min(bisect_right([p.height_mm for p in points], level_mm), len(points) - 1)
    low, high = points[upper - 1], points[upper]
    fraction = (level_mm - low.height_mm) / (high.height_mm - low.height_mm)
    return low.volume_l + fraction * (high.volume_l - low.volume_l)


def _check_table(table: StrappingTable) -> None:
    numbers = [table.range_low_mm, table.range_high_mm, table.max_height_mm]
    numbers += [n for p in table.points for n in (p.height_mm, p.volume_l)]
    if not all(math.isfinite(n) for n in numbers):
        raise ValueError("every height, volume and range must be a finite number")
    if table.version < 1:
        raise ValueError("the table version must be 1 or more")
    if not 0 <= table.range_low_mm < table.range_high_mm:
        raise ValueError("the transducer range must rise from 0 mm or more")
    if len(table.points) < MIN_STRAPPING_POINTS:
        raise ValueError(f"a strapping table needs at least {MIN_STRAPPING_POINTS} points")
    if table.points[0].height_mm < 0 or table.points[0].volume_l < 0:
        raise ValueError("the first strapping point must not be negative")
    for low, high in pairwise(table.points):
        if not (high.height_mm > low.height_mm and high.volume_l > low.volume_l):
            raise ValueError("strapping points must rise in both height and volume")
    if table.points[-1].height_mm > table.max_height_mm:
        raise ValueError("the strapping points must end at or below the tank's full height")
