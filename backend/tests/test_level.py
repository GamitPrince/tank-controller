"""Level height, level % and volume from the radar loop current (S-082).

TEST TABLE ONLY. The strapping table below is made up for these tests: it is
not the pilot tank or any customer's tank, whose real table is customer data
and never enters this repository. Its points are evenly spaced, and its bottom
zone rises slowly, as a dished head and heating coils would make it.
"""

from dataclasses import replace

import pytest

from tankapi.level import (
    CALCULATION_VERSION,
    LevelStatus,
    StrappingPoint,
    StrappingTable,
    compute_level,
)
from tankapi.records import Quality, Reading

RADAR = 1001
PRESSURE = 1002
POINTS = tuple(
    StrappingPoint(height, volume)
    for height, volume in [
        (0, 0),
        (250, 180),
        (500, 520),
        (750, 1000),
        (1000, 1500),
        (1250, 2000),
        (1500, 2500),
        (1750, 3000),
        (2000, 3500),
    ]
)
# 0 mm at 4 mA and 3200 mm at 20 mA: 5 microamps per millimetre.
TABLE = StrappingTable(
    version=3, range_low_mm=0, range_high_mm=3200, max_height_mm=2000, points=POINTS
)


def radar(current_ua: int | bool | None, quality: Quality = Quality.GOOD) -> Reading:
    return Reading(RADAR, quality, 0, current_ua)


def microamps(level_mm: float) -> int:
    return round(4_000 + 5 * level_mm)


def test_status_values_are_those_s035_resolved() -> None:
    assert {status.value for status in LevelStatus} == {"ok", "fault", "out_of_range", "stale"}


@pytest.mark.parametrize(
    ("level_mm", "volume_l"),
    [(100, 72), (600, 712), (1100, 1700), (1999, 3498)],
)
def test_a_good_reading_gives_hand_calculated_figures(level_mm: float, volume_l: float) -> None:
    result = compute_level(radar(microamps(level_mm)), TABLE)

    assert result.status is LevelStatus.OK
    assert result.level_mm == pytest.approx(level_mm, rel=1e-9)
    assert result.level_percent == pytest.approx(level_mm / 20, rel=1e-9)
    assert result.volume_l == pytest.approx(volume_l, rel=1e-9)
    assert result.table_version == 3
    assert result.calculation_version == CALCULATION_VERSION


@pytest.mark.parametrize("point", POINTS)
def test_every_strapping_point_is_reproduced(point: StrappingPoint) -> None:
    result = compute_level(radar(microamps(point.height_mm)), TABLE)

    assert result.status is LevelStatus.OK
    assert result.volume_l == pytest.approx(point.volume_l, abs=1e-9)


def test_the_full_height_is_one_hundred_percent() -> None:
    result = compute_level(radar(microamps(2000)), TABLE)

    assert result.level_percent == pytest.approx(100.0)


def test_the_transducer_range_low_end_offsets_the_level() -> None:
    raised = replace(TABLE, range_low_mm=100, range_high_mm=3300)

    assert compute_level(radar(4_000), raised).level_mm == pytest.approx(100.0)


@pytest.mark.parametrize(
    ("table", "current_ua"),
    [
        (TABLE, microamps(2001)),  # above the tank's full height
        (TABLE, 20_000),  # the transducer reaches past the tank
        (replace(TABLE, points=POINTS[1:]), 4_000),  # below the lowest point
    ],
)
def test_a_level_outside_the_table_is_out_of_range(table: StrappingTable, current_ua: int) -> None:
    result = compute_level(radar(current_ua), table)

    assert result.status is LevelStatus.OUT_OF_RANGE
    assert (result.level_mm, result.level_percent, result.volume_l) == (None, None, None)


@pytest.mark.parametrize(
    ("quality", "current_ua", "status"),
    [
        (Quality.STALE, 9_500, LevelStatus.STALE),
        (Quality.OUT_OF_RANGE, 3_800, LevelStatus.OUT_OF_RANGE),
        (Quality.OUT_OF_RANGE, 20_500, LevelStatus.OUT_OF_RANGE),
        (Quality.FAULT, None, LevelStatus.FAULT),
        (Quality.UNCONFIGURED, None, LevelStatus.FAULT),
        (Quality.GOOD, 3_999, LevelStatus.OUT_OF_RANGE),
        (Quality.GOOD, 20_001, LevelStatus.OUT_OF_RANGE),
        (Quality.GOOD, True, LevelStatus.FAULT),
    ],
)
def test_an_unusable_reading_gives_a_status_and_no_figures(
    quality: Quality, current_ua: int | bool | None, status: LevelStatus
) -> None:
    result = compute_level(radar(current_ua, quality), TABLE)

    assert result.status is status
    assert (result.level_mm, result.level_percent, result.volume_l) == (None, None, None)
    assert (result.table_version, result.calculation_version) == (3, CALCULATION_VERSION)


def test_the_pressure_level_is_refused() -> None:
    with pytest.raises(ValueError, match="not the radar level"):
        compute_level(Reading(PRESSURE, Quality.GOOD, 0, 9_500), TABLE)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": 0}, "version"),
        ({"range_low_mm": 3200}, "transducer range"),
        ({"range_low_mm": -1}, "transducer range"),
        ({"range_high_mm": float("nan")}, "finite"),
        ({"points": POINTS[:1]}, "at least 2"),
        ({"points": (StrappingPoint(-1, 0), *POINTS[1:])}, "not be negative"),
        ({"points": (StrappingPoint(0, -1), *POINTS[1:])}, "not be negative"),
        ({"points": (*POINTS[:2], StrappingPoint(250, 600))}, "rise"),
        ({"points": (*POINTS[:2], StrappingPoint(300, 180))}, "rise"),
        ({"points": (*POINTS[:2], StrappingPoint(float("nan"), 600))}, "finite"),
        ({"points": (*POINTS[:2], StrappingPoint(300, float("inf")))}, "finite"),
        ({"max_height_mm": 1999}, "full height"),
    ],
)
def test_a_broken_table_is_refused(change: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(TABLE, **change)
