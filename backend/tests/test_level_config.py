"""A tank's stored level configuration: the schema's rules (S-085) and the read helper (S-086).

TEST DATA ONLY. Every customer, tank and strapping table here is made up; a
real tank's table is customer data and never enters this repository.
"""

import math

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.db import CustomerRow, LevelConfigRow, PlantRow, StrappingPointRow, TankRow
from tankapi.level import (
    CALCULATION_VERSION,
    LevelStatus,
    StrappingPoint,
    StrappingTable,
    compute_level,
)
from tankapi.level_config import LevelConfig, LevelConfigError, level_config_at
from tankapi.records import Quality, Reading

CONFIGURED = 1_763_683_200
CHANGED = CONFIGURED + 86_400
POINTS = ((0.0, 0.0), (250.0, 180.0), (500.0, 520.0), (750.0, 1000.0), (2000.0, 3500.0))
# 0 mm at 4 mA and 3200 mm at 20 mA: 5 microamps per millimetre.
RANGE = {"range_low_mm": 0.0, "range_high_mm": 3200.0, "max_height_mm": 2000.0}

Previous = tuple[int, float, float] | None


def config(row_id: int, tank_id: int, version: int, start: int, end: int | None = None, **numbers):
    return LevelConfigRow(
        id=row_id,
        tank_id=tank_id,
        version=version,
        calculation_version=numbers.pop("calculation_version", CALCULATION_VERSION),
        valid_from_unix_s=start,
        valid_to_unix_s=end,
        **(RANGE | numbers),
    )


def point(config_id: int, position: int, height: float, volume: float, previous: Previous = None):
    before = previous or (None, None, None)
    return StrappingPointRow(
        configuration_id=config_id,
        position=position,
        height_mm=height,
        volume_l=volume,
        previous_position=before[0],
        previous_height_mm=before[1],
        previous_volume_l=before[2],
    )


def chained(config_id: int, points: tuple[tuple[float, float], ...]) -> list[StrappingPointRow]:
    """The points as rows, each repeating the one before it, as a writer must store them."""
    rows: list[StrappingPointRow] = []
    for position, (height, volume) in enumerate(points):
        previous = (position - 1, *points[position - 1]) if position else None
        rows.append(point(config_id, position, height, volume, previous))
    return rows


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


def at(engine: Engine, tank_id: int, unix_time_s: int) -> LevelConfig | None:
    with Session(engine) as session:
        return level_config_at(session, tank_id, unix_time_s)


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Example Co's Tank 1 configured from CONFIGURED; Tank 2 has no configuration."""
    add(engine, CustomerRow(id=1, name="Example Co"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"), TankRow(id=2, plant_id=1, name="Tank 2"))
    add(engine, config(1, 1, 1, CONFIGURED))
    add(engine, *chained(1, POINTS))
    return engine


def test_a_configuration_keeps_its_numbers_and_its_points_in_order(site: Engine) -> None:
    with Session(site) as session:
        row = session.scalars(select(LevelConfigRow)).one()
        stored = [(p.position, p.height_mm, p.volume_l) for p in row.points]
        numbers = (row.range_low_mm, row.range_high_mm, row.max_height_mm)
    assert stored == [(n, *p) for n, p in enumerate(POINTS)]
    assert numbers == (0.0, 3200.0, 2000.0)


def test_a_change_closes_one_configuration_and_opens_the_next(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(LevelConfigRow).values(valid_to_unix_s=CHANGED))
        session.commit()
    add(site, config(2, 1, 2, CHANGED, max_height_mm=2500.0))
    add(site, *chained(2, (*POINTS, (2500.0, 4400.0))))
    with Session(site) as session:
        query = select(LevelConfigRow.version, LevelConfigRow.valid_to_unix_s)
        assert session.execute(query.order_by(LevelConfigRow.version)).all() == [
            (1, CHANGED),
            (2, None),
        ]


def test_a_configured_tank_gives_its_table_and_calculation_version(site: Engine) -> None:
    table = StrappingTable(1, 0.0, 3200.0, 2000.0, tuple(StrappingPoint(*p) for p in POINTS))
    assert at(site, 1, CONFIGURED) == LevelConfig(CALCULATION_VERSION, table)
    assert at(site, 1, CHANGED) == LevelConfig(CALCULATION_VERSION, table)


@pytest.mark.parametrize(
    ("level_mm", "percent", "volume_l"),
    [(0, 0.0, 0.0), (500, 25.0, 520.0), (625, 31.25, 760.0), (1375, 68.75, 2250.0)],
)
def test_the_stored_table_gives_figures_at_and_between_its_points(
    site: Engine, level_mm: int, percent: float, volume_l: float
) -> None:
    reading = Reading(1001, Quality.GOOD, 0, 4_000 + 5 * level_mm)
    result = compute_level(reading, at(site, 1, CONFIGURED).table)
    assert (result.status, result.level_percent) == (LevelStatus.OK, percent)
    assert result.volume_l == pytest.approx(volume_l)


def test_the_helper_gives_the_configuration_in_force_at_each_time(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(LevelConfigRow).values(valid_to_unix_s=CHANGED))
        session.commit()
    add(site, config(2, 1, 2, CHANGED, max_height_mm=2500.0))
    add(site, *chained(2, (*POINTS, (2500.0, 4400.0))))
    assert at(site, 1, CHANGED - 1).table.version == 1
    assert at(site, 1, CHANGED).table.max_height_mm == 2500.0
    assert at(site, 1, CONFIGURED - 1) is None
    assert at(site, 2, CONFIGURED) is None
    assert at(site, 9, CONFIGURED) is None


def test_overlapping_configurations_raise_instead_of_picking_one(site: Engine) -> None:
    add(site, config(2, 2, 1, 0, CHANGED), config(3, 2, 2, CONFIGURED, CHANGED))
    with pytest.raises(LevelConfigError, match="overlapping"):
        at(site, 2, CONFIGURED)


@pytest.mark.parametrize(
    ("points", "refusal"),
    [(((0.0, 0.0),), "at least 2 points"), (((0.0, 0.0), (2100.0, 50.0)), "full height")],
)
def test_a_stored_table_that_compute_level_refuses_raises(
    site: Engine, points: tuple[tuple[float, float], ...], refusal: str
) -> None:
    add(site, config(2, 2, 1, CONFIGURED))
    add(site, *chained(2, points))
    with pytest.raises(LevelConfigError, match=refusal):
        at(site, 2, CONFIGURED)


@pytest.mark.parametrize("unix_time_s", [None, True, 1.5])
def test_a_time_that_is_not_whole_seconds_is_refused(site: Engine, unix_time_s: object) -> None:
    with pytest.raises(TypeError):
        at(site, 1, unix_time_s)


@pytest.mark.parametrize(
    ("row", "refusal"),
    [
        # After configuration 2's points (0, 0) and (100, 50):
        (point(2, 2, 90.0, 60.0, (1, 100.0, 50.0)), "CHECK"),  # height falls
        (point(2, 2, 200.0, 50.0, (1, 100.0, 50.0)), "CHECK"),  # volume flat
        (point(2, 2, 200.0, 80.0), "CHECK"),  # no previous point
        (point(2, 3, 200.0, 80.0, (1, 100.0, 50.0)), "CHECK"),  # not the one before
        (point(2, 2, 200.0, 80.0, (1, 99.0, 50.0)), "FOREIGN KEY"),  # a wrong copy
        (point(2, 3, 200.0, 80.0, (2, 150.0, 60.0)), "FOREIGN KEY"),  # a point missing
        # The first point of configuration 3, which has none yet:
        (point(3, 0, 0.0, 0.0, (0, 0.0, 0.0)), "CHECK"),
        (point(3, 0, -1.0, 0.0), "CHECK"),
        (point(3, 0, 0.0, math.inf), "CHECK"),
        (point(3, 0, math.nan, 0.0), "NOT NULL"),  # SQLite stores NaN as NULL
        (point(9, 0, 0.0, 0.0), "FOREIGN KEY"),
    ],
)
def test_a_strapping_point_breaking_the_rules_is_refused(
    site: Engine, row: StrappingPointRow, refusal: str
) -> None:
    add(site, config(2, 2, 1, CONFIGURED), config(3, 2, 2, 0, CONFIGURED))
    add(site, *chained(2, ((0.0, 0.0), (100.0, 50.0))))
    with pytest.raises(IntegrityError, match=refusal):
        add(site, row)


@pytest.mark.parametrize(
    ("row", "refusal"),
    [
        (config(2, 9, 1, CONFIGURED), "FOREIGN KEY"),
        (config(2, 1, 2, CHANGED), "UNIQUE"),  # a second open configuration
        (config(2, 1, 1, 0, CONFIGURED), "UNIQUE"),  # the same version again
        (config(2, 1, 2, CONFIGURED, CHANGED), "UNIQUE"),  # the same start again
        (config(2, 2, 0, CONFIGURED), "CHECK"),
        (config(2, 2, 1, CONFIGURED, calculation_version=0), "CHECK"),
        (config(2, 2, 1, CONFIGURED, CONFIGURED), "CHECK"),
        (config(2, 2, 1, -1), "CHECK"),
        (config(2, 2, 1, CONFIGURED, range_low_mm=3200.0, range_high_mm=0.0), "CHECK"),
        (config(2, 2, 1, CONFIGURED, range_low_mm=-1.0), "CHECK"),
        (config(2, 2, 1, CONFIGURED, range_high_mm=math.inf), "CHECK"),
        (config(2, 2, 1, CONFIGURED, max_height_mm=0.0), "CHECK"),
        (config(2, 2, 1, CONFIGURED, max_height_mm=math.inf), "CHECK"),
    ],
)
def test_a_configuration_breaking_the_rules_is_refused(
    site: Engine, row: LevelConfigRow, refusal: str
) -> None:
    with pytest.raises(IntegrityError, match=refusal):
        add(site, row)


def test_a_point_another_point_rests_on_cannot_be_changed_in_place(site: Engine) -> None:
    with Session(site) as session, pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.execute(
            update(StrappingPointRow).where(StrappingPointRow.position == 1).values(height_mm=1.0)
        )
        session.commit()
