"""A tank's stored alarm thresholds: the schema's rules (S-087).

TEST DATA ONLY. Every customer, tank and threshold here is made up.
"""

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.db import AlarmThresholdRow, CustomerRow, PlantRow, TankRow

SET = 1_763_683_200
CHANGED = SET + 86_400
RADAR, PRESSURE, UPPER_A, HIGH_HIGH, UPTIME = 1001, 1002, 2001, 3001, 9001


def threshold(row_id: int, start: int = SET, end: int | None = None, **fields) -> AlarmThresholdRow:
    """A warning high of 18 mA on Tank 1's radar unless ``fields`` say otherwise."""
    values = {
        "tank_id": 1,
        "measure": "signal",
        "signal_id": RADAR,
        "direction": "high",
        "alarm_class": "warning",
        "limit_value": 18_000,
        "deadband": 200,
    }
    return AlarmThresholdRow(
        id=row_id, valid_from_unix_s=start, valid_to_unix_s=end, **(values | fields)
    )


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Example Co's Tank 1 with one threshold from SET; Tank 2 has none."""
    add(engine, CustomerRow(id=1, name="Example Co"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"), TankRow(id=2, plant_id=1, name="Tank 2"))
    add(engine, threshold(1))
    return engine


def test_a_threshold_keeps_its_numbers(site: Engine) -> None:
    with Session(site) as session:
        row = session.scalars(select(AlarmThresholdRow)).one()
        stored = (row.measure, row.signal_id, row.direction, row.alarm_class)
        numbers = (row.limit_value, row.deadband, row.valid_from_unix_s, row.valid_to_unix_s)
    assert stored == ("signal", RADAR, "high", "warning")
    assert numbers == (18_000, 200, SET, None)


def test_a_change_closes_one_threshold_and_opens_the_next(site: Engine) -> None:
    with Session(site) as session:
        session.execute(update(AlarmThresholdRow).values(valid_to_unix_s=CHANGED))
        session.commit()
    add(site, threshold(2, CHANGED, limit_value=17_500))
    with Session(site) as session:
        query = select(AlarmThresholdRow.limit_value, AlarmThresholdRow.valid_to_unix_s)
        assert session.execute(query.order_by(AlarmThresholdRow.id)).all() == [
            (18_000, CHANGED),
            (17_500, None),
        ]


def test_each_class_direction_and_measure_may_have_its_own_open_threshold(site: Engine) -> None:
    add(
        site,
        threshold(2, alarm_class="critical", limit_value=19_000),
        threshold(3, direction="low", limit_value=4_500),
        threshold(4, measure="level_percent", limit_value=9_000, deadband=50),
        threshold(5, signal_id=UPPER_A, limit_value=-500),  # below 0 degrees, as measured
        threshold(6, tank_id=2),
    )
    with Session(site) as session:
        assert len(session.scalars(select(AlarmThresholdRow)).all()) == 6


@pytest.mark.parametrize(
    ("row", "refusal"),
    [
        (threshold(2, tank_id=9), "FOREIGN KEY"),
        (threshold(2, CHANGED), "UNIQUE"),  # a second open threshold of the same key
        (threshold(2, SET, CHANGED), "UNIQUE"),  # the same start again
        (threshold(2, measure="volume"), "CHECK"),
        (threshold(2, signal_id=HIGH_HIGH), "CHECK"),  # a device contact takes none
        (threshold(2, signal_id=UPTIME), "CHECK"),
        (threshold(2, measure="level_percent", signal_id=PRESSURE), "CHECK"),
        (threshold(2, direction="rising"), "CHECK"),
        (threshold(2, alarm_class="trip"), "CHECK"),
        (threshold(2, deadband=-1, tank_id=2), "CHECK"),
        (threshold(2, measure="level_percent", limit_value=10_001), "CHECK"),
        (threshold(2, measure="level_percent", limit_value=-1), "CHECK"),
        (threshold(2, measure="level_percent", limit_value=9_000, deadband=10_001), "CHECK"),
        (threshold(2, -1, tank_id=2), "CHECK"),
        (threshold(2, SET, SET, tank_id=2), "CHECK"),
        (threshold(2, limit_value=None, tank_id=2), "NOT NULL"),
        (threshold(2, deadband=None, tank_id=2), "NOT NULL"),
    ],
)
def test_a_threshold_breaking_the_rules_is_refused(
    site: Engine, row: AlarmThresholdRow, refusal: str
) -> None:
    with pytest.raises(IntegrityError, match=refusal):
        add(site, row)
