"""The customer > plant > tank > device tables (S-073) and resolving a device's owner (S-074).

Every customer, plant and tank name here is made up.
"""

import pytest
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.db import AssignmentRow, CustomerRow, DeviceRow, PlantRow, TankRow
from tankapi.ownership import (
    OverlappingAssignmentsError,
    Owner,
    Unowned,
    owner_at,
    owner_now,
)

CLAIMED = 1_763_683_200
MOVED = CLAIMED + 86_400
ON_TANK_1 = Owner(customer_id=1, plant_id=1, tank_id=1)
ON_TANK_2 = Owner(customer_id=1, plant_id=1, tank_id=2)


def assigned(device_id: str, tank_id: int, start: int, end: int | None = None) -> AssignmentRow:
    return AssignmentRow(
        device_id=device_id, tank_id=tank_id, valid_from_unix_s=start, valid_to_unix_s=end
    )


def add(engine: Engine, *rows: object) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


def move(engine: Engine, at_unix_s: int, to_tank: int | None) -> None:
    """Close DEV-1's open assignment and, unless ``to_tank`` is None, open the next."""
    with Session(engine) as session:
        session.execute(
            update(AssignmentRow)
            .where(AssignmentRow.device_id == "DEV-1", AssignmentRow.valid_to_unix_s.is_(None))
            .values(valid_to_unix_s=at_unix_s)
        )
        if to_tank is not None:
            session.add(assigned("DEV-1", to_tank, at_unix_s))
        session.commit()


def history(engine: Engine) -> list[tuple[int, int, int | None]]:
    """DEV-1's assignments, oldest first, as (tank, from, to)."""
    columns = (
        AssignmentRow.tank_id,
        AssignmentRow.valid_from_unix_s,
        AssignmentRow.valid_to_unix_s,
    )
    query = select(*columns).where(AssignmentRow.device_id == "DEV-1")
    with Session(engine) as session:
        return [tuple(row) for row in session.execute(query.order_by(columns[1]))]


@pytest.fixture
def site(engine: Engine) -> Engine:
    """Two customers; DEV-1 claimed onto Example Co's Tank 1, DEV-2 known but unclaimed."""
    add(engine, CustomerRow(id=1, name="Example Co"), CustomerRow(id=2, name="Sample Ltd"))
    add(engine, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(engine, PlantRow(id=2, customer_id=2, name="Plant A"))
    add(engine, TankRow(id=1, plant_id=1, name="Tank 1"), TankRow(id=2, plant_id=1, name="Tank 2"))
    add(engine, TankRow(id=3, plant_id=2, name="Tank 1"))
    add(engine, DeviceRow(device_id="DEV-1"), DeviceRow(device_id="DEV-2"))
    add(engine, assigned("DEV-1", 1, CLAIMED))
    return engine


def test_a_move_keeps_the_old_assignment_as_history(site: Engine) -> None:
    move(site, MOVED, to_tank=2)
    assert history(site) == [(1, CLAIMED, MOVED), (2, MOVED, None)]


def test_a_device_taken_off_its_tank_has_no_open_assignment(site: Engine) -> None:
    move(site, MOVED, to_tank=None)
    assert history(site) == [(1, CLAIMED, MOVED)]


@pytest.mark.parametrize(
    ("row", "refusal"),
    [
        (PlantRow(customer_id=9, name="Plant Z"), "FOREIGN KEY"),
        (TankRow(plant_id=9, name="Tank Z"), "FOREIGN KEY"),
        (assigned("DEV-9", 2, MOVED), "FOREIGN KEY"),
        (assigned("DEV-2", 9, MOVED), "FOREIGN KEY"),
        (CustomerRow(name="Example Co"), "UNIQUE"),
        (PlantRow(customer_id=1, name="Plant A"), "UNIQUE"),
        (TankRow(plant_id=1, name="Tank 1"), "UNIQUE"),
        (DeviceRow(device_id="DEV-1"), "UNIQUE"),
        # A second open assignment: a device is on one tank at a time.
        (assigned("DEV-1", 2, MOVED), "UNIQUE"),
        # A second assignment starting at the same instant.
        (assigned("DEV-1", 2, CLAIMED, MOVED), "UNIQUE"),
        (CustomerRow(name=""), "CHECK"),
        (TankRow(plant_id=1, name=""), "CHECK"),
        (DeviceRow(device_id=""), "CHECK"),
        (assigned("DEV-2", 2, -1), "CHECK"),
        (assigned("DEV-2", 2, MOVED, MOVED), "CHECK"),
    ],
)
def test_row_breaking_the_ownership_rules_is_refused(
    site: Engine, row: object, refusal: str
) -> None:
    with pytest.raises(IntegrityError, match=refusal):
        add(site, row)


def test_customer_with_plants_cannot_be_deleted(site: Engine) -> None:
    with Session(site) as session, pytest.raises(IntegrityError, match="FOREIGN KEY"):
        session.execute(delete(CustomerRow).where(CustomerRow.id == 1))
        session.commit()


def now(engine: Engine, device_id: str) -> Owner | Unowned:
    with Session(engine) as session:
        return owner_now(session, device_id)


def at(engine: Engine, device_id: str, unix_time_s: int) -> Owner | Unowned:
    with Session(engine) as session:
        return owner_at(session, device_id, unix_time_s)


def test_claimed_device_resolves_to_its_tank_plant_and_customer(site: Engine) -> None:
    add(site, assigned("DEV-2", 3, CLAIMED))
    assert now(site, "DEV-1") == ON_TANK_1
    assert now(site, "DEV-2") == Owner(customer_id=2, plant_id=2, tank_id=3)


def test_assignment_holds_from_its_start_and_not_before(site: Engine) -> None:
    assert at(site, "DEV-1", CLAIMED - 1) is Unowned.UNCLAIMED
    assert at(site, "DEV-1", CLAIMED) == ON_TANK_1


def test_moved_device_keeps_its_old_tank_for_the_time_it_was_there(site: Engine) -> None:
    move(site, MOVED, to_tank=2)
    assert now(site, "DEV-1") == ON_TANK_2
    assert at(site, "DEV-1", CLAIMED) == ON_TANK_1
    assert at(site, "DEV-1", MOVED - 1) == ON_TANK_1
    # The old assignment's end is excluded: at the move the device is on the new tank.
    assert at(site, "DEV-1", MOVED) == ON_TANK_2


def test_released_device_is_unclaimed_from_its_release_on(site: Engine) -> None:
    move(site, MOVED, to_tank=None)
    assert now(site, "DEV-1") is Unowned.UNCLAIMED
    assert at(site, "DEV-1", MOVED - 1) == ON_TANK_1
    assert at(site, "DEV-1", MOVED) is Unowned.UNCLAIMED
    assert at(site, "DEV-1", MOVED + 86_400) is Unowned.UNCLAIMED


def test_known_but_never_claimed_device_is_unclaimed(site: Engine) -> None:
    assert now(site, "DEV-2") is Unowned.UNCLAIMED
    assert at(site, "DEV-2", CLAIMED) is Unowned.UNCLAIMED


def test_device_missing_from_devices_is_unknown(site: Engine) -> None:
    assert now(site, "DEV-9") is Unowned.UNKNOWN
    assert at(site, "DEV-9", CLAIMED) is Unowned.UNKNOWN


def test_overlapping_assignments_raise_instead_of_picking_a_customer(site: Engine) -> None:
    # The schema refuses a second open row, not overlap among closed rows (S-073 [Confirm] 4).
    add(site, assigned("DEV-2", 2, CLAIMED, CLAIMED + 10), assigned("DEV-2", 3, CLAIMED + 5, MOVED))
    assert at(site, "DEV-2", CLAIMED + 4) == ON_TANK_2
    with pytest.raises(OverlappingAssignmentsError, match="DEV-2"):
        at(site, "DEV-2", CLAIMED + 5)


@pytest.mark.parametrize("untimed", [None, True, float(CLAIMED)])
def test_time_that_is_not_whole_unix_seconds_is_refused(site: Engine, untimed: object) -> None:
    # An untimed scan has no t; it must not fall back to the current tank (S-073 [Confirm] 3).
    with pytest.raises(TypeError, match="untimed"):
        at(site, "DEV-1", untimed)
