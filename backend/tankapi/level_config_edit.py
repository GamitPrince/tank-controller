"""Setting a tank's level configuration (S-103, P1-04).

``PUT /v1/tanks/{tank_id}/level-configuration`` with the transducer range, the
tank's full height, the strapping points and the calculation version sets the
configuration that the level % and volume are computed with (S-086) from the
server's second on: the configuration in force is closed and the next opened
(``tankapi.settings_edit``), with the next version number, chosen here. A
reading from before the change is still computed with the old configuration.

The body must make a ``StrappingTable`` (S-082): finite numbers, a range rising
from 0 mm, at least two points rising in height and volume, none above the full
height; every number is at most S-085's ceiling, and the calculation version is
the backend's own (S-101 [Confirm] 3). The level display lives in the cloud;
nothing here reaches a device.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.auth import Caller, require_caller
from tankapi.db import LevelConfigRow, StrappingPointRow
from tankapi.level import CALCULATION_VERSION, StrappingPoint, StrappingTable
from tankapi.session import get_session
from tankapi.settings_edit import (
    MS_PER_S,
    now_ms,
    record_change,
    refuse,
    require_editor,
    too_soon,
)

KIND = "level_configuration"
# Migration 0005's ceiling on every number, which also keeps out NaN and infinity.
CEILING = 1e9
MAX_POINTS = 200
Number = Annotated[float, Field(ge=0, le=CEILING, allow_inf_nan=False)]


class PointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height_mm: Number
    volume_l: Number


class LevelConfigRequest(BaseModel):
    """The range at 4 and 20 mA, the full height and the points, in mm and litres."""

    model_config = ConfigDict(extra="forbid")

    calculation_version: int
    range_low_mm: Number
    range_high_mm: Number
    max_height_mm: Number
    points: list[PointRequest] = Field(max_length=MAX_POINTS)


class LevelConfigSet(LevelConfigRequest):
    """The configuration now in force: its row ID and version, the server second it holds
    from, and the row it replaced, if any."""

    id: int
    version: int
    valid_from: int
    replaced: int | None


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]
CallerDependency = Annotated[Caller, Depends(require_caller)]


@router.put("/tanks/{tank_id}/level-configuration")
def set_level_config(
    session: SessionDependency,
    caller: CallerDependency,
    tank_id: Annotated[int, Path(ge=1)],
    body: LevelConfigRequest,
) -> LevelConfigSet:
    """Sets the tank's level configuration from now on; 409 if it changed this second."""
    require_editor(session, caller, tank_id)
    version = _next_version(session, tank_id)
    _check(body, version)
    at_ms = now_ms()
    start = at_ms // MS_PER_S
    current = session.scalars(
        select(LevelConfigRow).where(
            LevelConfigRow.tank_id == tank_id, LevelConfigRow.valid_to_unix_s.is_(None)
        )
    ).first()
    if current is not None and current.valid_from_unix_s >= start:
        raise too_soon()
    before = None if current is None else (current.id, _values(current))
    numbers = body.model_dump(exclude={"points"})
    row = LevelConfigRow(tank_id=tank_id, version=version, valid_from_unix_s=start, **numbers)
    try:
        if current is not None:
            current.valid_to_unix_s = start
            session.flush()  # closed before the next opens, for the one-open-row index
        session.add(row)
        session.flush()
        session.add_all(_chained(row.id, body.points))
        session.flush()
        session.refresh(row)
        record_change(session, caller, at_ms, tank_id, KIND, before, (row.id, _values(row)))
        session.commit()
    except IntegrityError:
        # A configuration already starts at this second, or a concurrent change won.
        session.rollback()
        raise too_soon() from None
    replaced = None if before is None else before[0]
    fields = body.model_dump() | {"id": row.id, "version": version}
    return LevelConfigSet(**fields, valid_from=start, replaced=replaced)


def _next_version(session: Session, tank_id: int) -> int:
    newest = select(func.max(LevelConfigRow.version)).where(LevelConfigRow.tank_id == tank_id)
    return (session.scalar(newest) or 0) + 1


def _check(body: LevelConfigRequest, version: int) -> None:
    if body.calculation_version != CALCULATION_VERSION:
        raise refuse(f"the calculation version is {CALCULATION_VERSION}")
    points = tuple(StrappingPoint(p.height_mm, p.volume_l) for p in body.points)
    numbers = body.model_dump(exclude={"points", "calculation_version"})
    try:
        StrappingTable(version=version, points=points, **numbers)
    except ValueError as error:
        raise refuse(str(error)) from None


def _chained(config_id: int, points: list[PointRequest]) -> list[StrappingPointRow]:
    """The points as rows, each repeating the one before it, as migration 0005 asks."""
    rows = []
    for position, point in enumerate(points):
        previous = points[position - 1] if position else None
        rows.append(
            StrappingPointRow(
                configuration_id=config_id,
                position=position,
                height_mm=point.height_mm,
                volume_l=point.volume_l,
                previous_position=None if previous is None else position - 1,
                previous_height_mm=None if previous is None else previous.height_mm,
                previous_volume_l=None if previous is None else previous.volume_l,
            )
        )
    return rows


def _values(row: LevelConfigRow) -> dict:
    """What the change log keeps of a configuration: its numbers, points and start."""
    columns = ("version", "calculation_version", "range_low_mm", "range_high_mm", "max_height_mm")
    points = [[p.height_mm, p.volume_l] for p in row.points]
    return {name: getattr(row, name) for name in columns} | {
        "points": points,
        "valid_from": row.valid_from_unix_s,
    }
