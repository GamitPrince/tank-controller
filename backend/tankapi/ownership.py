"""Which tank, plant and customer a device is on, now or at a given time (S-074).

ADR-0007 decision 2 holds every user, query and device to its own customer, and
ADR-0008 decision 3 has the backend check that on every request. A device is
unclaimed until an admin assigns it to a tank (ADR-0005 decision 2), and a move
keeps the old assignment (S-073), so a reading belongs to the tank the device
was on at the scan's ``t``. The login story asks this before it shows records.

An assignment holds over ``[valid_from_unix_s, valid_to_unix_s)``: its start is
included and its end is not, so at the instant of a move the device is already
on the new tank. The row with no end is the current assignment (S-073).

There is no single "now or at this time" call that ``None`` could switch: an
untimed scan (``tk`` false) has no ``unix_time_s``, and it must never be placed
on the current tank by its arrival time (S-073 ``[Confirm]`` 3). ``owner_at``
takes whole Unix seconds and refuses anything else.

Nothing here writes. Claiming, moving, releasing and the audit trail are later
stories.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import Session

from tankapi.db import AssignmentRow, DeviceRow, PlantRow, TankRow


@dataclass(frozen=True)
class Owner:
    """Where a device is: its tank, that tank's plant and that plant's customer."""

    customer_id: int
    plant_id: int
    tank_id: int


class Unowned(Enum):
    """Why a device has no owner. Either way, no customer may see its records."""

    UNKNOWN = "unknown"  # not in ``devices``
    UNCLAIMED = "unclaimed"  # in ``devices``, but on no tank at that time


class OverlappingAssignmentsError(RuntimeError):
    """More than one assignment holds at once, so the owner cannot be told."""


def owner_now(session: Session, device_id: str) -> Owner | Unowned:
    """The device's owner by its current assignment, the one with no end."""
    return _resolve(session, device_id, AssignmentRow.valid_to_unix_s.is_(None))


def owner_at(session: Session, device_id: str, unix_time_s: int) -> Owner | Unowned:
    """The device's owner at ``unix_time_s`` (Unix seconds, UTC), such as a scan's ``t``."""
    if isinstance(unix_time_s, bool) or not isinstance(unix_time_s, int):
        raise TypeError("unix_time_s must be whole Unix seconds; an untimed scan has no owner")
    ends = AssignmentRow.valid_to_unix_s
    held = and_(
        AssignmentRow.valid_from_unix_s <= unix_time_s,
        or_(ends.is_(None), ends > unix_time_s),
    )
    return _resolve(session, device_id, held)


def _resolve(session: Session, device_id: str, held: ColumnElement[bool]) -> Owner | Unowned:
    query = (
        select(PlantRow.customer_id, PlantRow.id, TankRow.id)
        .join(TankRow, TankRow.plant_id == PlantRow.id)
        .join(AssignmentRow, AssignmentRow.tank_id == TankRow.id)
        .where(AssignmentRow.device_id == device_id, held)
        .limit(2)
    )
    rows = session.execute(query).all()
    if len(rows) > 1:
        # Picking one could show one customer's data to another (S-073 [Confirm] 4).
        raise OverlappingAssignmentsError(f"device {device_id!r} has overlapping assignments")
    if rows:
        return Owner(*rows[0])
    known = session.get(DeviceRow, device_id) is not None
    return Unowned.UNCLAIMED if known else Unowned.UNKNOWN
