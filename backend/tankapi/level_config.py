"""The level configuration a tank had at a given time (S-086, on S-085's tables).

``tankapi.level.compute_level`` (S-082) needs a tank's transducer range, full
height and strapping table. They are stored with their history (migration
0005): a correction closes one configuration and opens the next, so a reading
is computed with the configuration in force at its scan's ``t`` and a past
figure never changes silently (S-035). Each configuration also names the
calculation version it is used with (ADR-0007 decision 9).

A configuration holds over ``[valid_from_unix_s, valid_to_unix_s)``, as a
device assignment does (S-074). The stored table is checked again by
``StrappingTable`` when it is read, which covers what the schema cannot: at
least two points, and none above the tank's full height.

Nothing here writes. Entering and changing a configuration, with its audit
entry, is a later admin story.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from tankapi.db import LevelConfigRow
from tankapi.level import StrappingPoint, StrappingTable


@dataclass(frozen=True)
class LevelConfig:
    """One stored configuration: its table, and the calculation version it is used with."""

    calculation_version: int
    table: StrappingTable


class LevelConfigError(RuntimeError):
    """A tank's stored configuration cannot be used: two hold at once, or its table is broken."""


def level_config_at(session: Session, tank_id: int, unix_time_s: int) -> LevelConfig | None:
    """The tank's configuration at ``unix_time_s`` (Unix seconds, UTC), or ``None`` if none.

    Two configurations holding at once raise :class:`LevelConfigError` instead of
    picking one, and so does a stored table that ``StrappingTable`` refuses.
    """
    if isinstance(unix_time_s, bool) or not isinstance(unix_time_s, int):
        raise TypeError("unix_time_s must be whole Unix seconds; an untimed scan has none")
    ends = LevelConfigRow.valid_to_unix_s
    query = (
        select(LevelConfigRow)
        .options(selectinload(LevelConfigRow.points))
        .where(
            LevelConfigRow.tank_id == tank_id,
            LevelConfigRow.valid_from_unix_s <= unix_time_s,
            or_(ends.is_(None), ends > unix_time_s),
        )
        .limit(2)
    )
    rows = session.scalars(query).all()
    if len(rows) > 1:
        raise LevelConfigError(f"tank {tank_id} has overlapping level configurations")
    return _config(rows[0]) if rows else None


def _config(row: LevelConfigRow) -> LevelConfig:
    points = tuple(StrappingPoint(p.height_mm, p.volume_l) for p in row.points)
    try:
        table = StrappingTable(
            version=row.version,
            range_low_mm=row.range_low_mm,
            range_high_mm=row.range_high_mm,
            max_height_mm=row.max_height_mm,
            points=points,
        )
    except ValueError as error:
        message = f"tank {row.tank_id} level configuration {row.version} is broken: {error}"
        raise LevelConfigError(message) from error
    return LevelConfig(row.calculation_version, table)
