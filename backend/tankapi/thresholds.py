"""The alarm thresholds a tank had at a given time (S-089, on S-087's table).

Thresholds are stored with their history (migration 0006): a change closes one
row and opens the next, so a scan is judged against the thresholds in force at
its own ``t``, never at its arrival, and a past alarm keeps the limit it was
raised against. A row holds over ``[valid_from_unix_s, valid_to_unix_s)``, as a
level configuration does (S-086).

An alarm is one threshold key: tank, measure, signal, direction and class. A
changed limit is a new row with the same key, so the alarm keeps its state
across the change. Two rows of one key holding at once raise
:class:`ThresholdError` rather than pick one.

Nothing here writes. Setting thresholds, with its audit entry, is a later admin
story.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tankapi.alarm_rules import AlarmClass, Direction, Measure, Threshold
from tankapi.db import AlarmThresholdRow

# The columns of db.THRESHOLD_KEY: tank, measure, signal, direction and class.
AlarmKey = tuple[int, str, int, str, str]


@dataclass(frozen=True)
class ThresholdInForce:
    """One stored threshold row: its ID (the version in force) and its rule."""

    id: int
    tank_id: int
    threshold: Threshold

    @property
    def key(self) -> AlarmKey:
        """The alarm this threshold belongs to, the same across a change of limit."""
        rule = self.threshold
        measure, direction, alarm_class = rule.measure, rule.direction, rule.alarm_class
        return (self.tank_id, measure.value, rule.signal_id, direction.value, alarm_class.value)


class ThresholdError(RuntimeError):
    """A tank's stored thresholds cannot be used: two rows of one key hold at once."""


def thresholds_at(session: Session, tank_id: int, unix_time_s: int) -> list[ThresholdInForce]:
    """The tank's thresholds at ``unix_time_s`` (Unix seconds, UTC), oldest row first."""
    if isinstance(unix_time_s, bool) or not isinstance(unix_time_s, int):
        raise TypeError("unix_time_s must be whole Unix seconds; an untimed scan has none")
    ends = AlarmThresholdRow.valid_to_unix_s
    query = (
        select(AlarmThresholdRow)
        .where(
            AlarmThresholdRow.tank_id == tank_id,
            AlarmThresholdRow.valid_from_unix_s <= unix_time_s,
            or_(ends.is_(None), ends > unix_time_s),
        )
        .order_by(AlarmThresholdRow.id)
    )
    found = [_in_force(row) for row in session.scalars(query)]
    if len({item.key for item in found}) < len(found):
        raise ThresholdError(f"tank {tank_id} has overlapping thresholds of one kind")
    return found


def _in_force(row: AlarmThresholdRow) -> ThresholdInForce:
    threshold = Threshold(
        measure=Measure(row.measure),
        signal_id=row.signal_id,
        direction=Direction(row.direction),
        alarm_class=AlarmClass(row.alarm_class),
        limit=row.limit_value,
        deadband=row.deadband,
    )
    return ThresholdInForce(row.id, row.tank_id, threshold)
