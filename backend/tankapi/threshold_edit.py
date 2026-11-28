"""Setting one of a tank's advisory alarm thresholds (S-102, P1-18).

``PUT /v1/tanks/{tank_id}/alarm-thresholds`` with one threshold's measure,
signal, direction, class, limit and deadband sets that alarm's limit from the
server's second on: the row in force for the same tank, measure, signal,
direction and class is closed and a new one opened (``tankapi.settings_edit``).
The alarm keeps its key, so its raised or cleared state carries over, and no
stored scan or alarm event is judged again (S-101 [Confirm] 4).

Besides S-087's rules (``Threshold``), a signal's limit lies within its valid
range in the transmitted unit (``interfaces/signals-v1.yaml``), and a low limit
lies below the high limit of the same measure, signal and class in force, and
the reverse (S-101 [Confirm] 3). These are cloud alarms for people; nothing
here reaches a device or the hardwired safety chain.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.alarm_rules import AlarmClass, Direction, Measure, Threshold
from tankapi.auth import Caller, require_caller
from tankapi.db import AlarmThresholdRow
from tankapi.session import get_session
from tankapi.settings_edit import (
    MS_PER_S,
    now_ms,
    record_change,
    refuse,
    require_editor,
    too_soon,
)

KIND = "alarm_threshold"
MICROAMPS = (4_000, 20_000)  # 4 to 20 mA
CENTI_DEGREES = (0, 20_000)  # 0 to 200 degrees C
# Each threshold signal's valid range in its transmitted unit (signals-v1.yaml).
SIGNAL_RANGES = {1001: MICROAMPS, 1002: MICROAMPS} | {s: CENTI_DEGREES for s in range(2001, 2007)}
OPPOSITE = {Direction.HIGH: Direction.LOW, Direction.LOW: Direction.HIGH}


class ThresholdRequest(BaseModel):
    """One threshold, numbers in the measure's stored unit (S-087)."""

    model_config = ConfigDict(extra="forbid")

    measure: Measure
    signal_id: int
    direction: Direction
    alarm_class: AlarmClass
    limit: int
    deadband: int


class ThresholdSet(ThresholdRequest):
    """The threshold now in force: its row ID, the server second it holds from, and the row
    it replaced, if any."""

    id: int
    valid_from: int
    replaced: int | None


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]
CallerDependency = Annotated[Caller, Depends(require_caller)]


@router.put("/tanks/{tank_id}/alarm-thresholds")
def set_threshold(
    session: SessionDependency,
    caller: CallerDependency,
    tank_id: Annotated[int, Path(ge=1)],
    body: ThresholdRequest,
) -> ThresholdSet:
    """Sets one alarm's threshold from now on; 409 if it changed this second."""
    require_editor(session, caller, tank_id)
    rule = _rule(body)
    at_ms = now_ms()
    start = at_ms // MS_PER_S
    current, opposite = _open_rows(session, tank_id, rule)
    _check_against(rule, opposite)
    if current is not None and current.valid_from_unix_s >= start:
        raise too_soon()
    before = None if current is None else (current.id, _values(current))
    row = AlarmThresholdRow(tank_id=tank_id, valid_from_unix_s=start, **_columns(rule))
    try:
        if current is not None:
            current.valid_to_unix_s = start
            session.flush()  # closed before the next opens, for the one-open-row index
        session.add(row)
        session.flush()
        record_change(session, caller, at_ms, tank_id, KIND, before, (row.id, _values(row)))
        session.commit()
    except IntegrityError:
        # A row of this alarm already starts at this second, or a concurrent change won.
        session.rollback()
        raise too_soon() from None
    replaced = None if before is None else before[0]
    return ThresholdSet(**body.model_dump(), id=row.id, valid_from=start, replaced=replaced)


def _rule(body: ThresholdRequest) -> Threshold:
    try:
        rule = Threshold(**body.model_dump())
    except ValueError as error:
        raise refuse(str(error)) from None
    if rule.measure is Measure.SIGNAL:
        low, high = SIGNAL_RANGES[rule.signal_id]
        if not low <= rule.limit <= high or rule.deadband > high - low:
            raise refuse(f"a limit on signal {rule.signal_id} lies within {low} to {high}")
    return rule


def _open_rows(
    session: Session, tank_id: int, rule: Threshold
) -> tuple[AlarmThresholdRow | None, AlarmThresholdRow | None]:
    """The open row of this alarm, and of its other direction in the same class."""
    query = select(AlarmThresholdRow).where(
        AlarmThresholdRow.tank_id == tank_id,
        AlarmThresholdRow.measure == rule.measure.value,
        AlarmThresholdRow.signal_id == rule.signal_id,
        AlarmThresholdRow.alarm_class == rule.alarm_class.value,
        AlarmThresholdRow.valid_to_unix_s.is_(None),
    )
    rows = {row.direction: row for row in session.scalars(query)}
    return rows.get(rule.direction.value), rows.get(OPPOSITE[rule.direction].value)


def _check_against(rule: Threshold, opposite: AlarmThresholdRow | None) -> None:
    if opposite is None:
        return
    if rule.direction is Direction.LOW and rule.limit >= opposite.limit_value:
        raise refuse(f"a low limit must lie below the high limit of {opposite.limit_value}")
    if rule.direction is Direction.HIGH and rule.limit <= opposite.limit_value:
        raise refuse(f"a high limit must lie above the low limit of {opposite.limit_value}")


def _columns(rule: Threshold) -> dict:
    return {
        "measure": rule.measure.value,
        "signal_id": rule.signal_id,
        "direction": rule.direction.value,
        "alarm_class": rule.alarm_class.value,
        "limit_value": rule.limit,
        "deadband": rule.deadband,
    }


def _values(row: AlarmThresholdRow) -> dict:
    """What the change log keeps of a row: its rule and the second it holds from."""
    columns = ("measure", "signal_id", "direction", "alarm_class", "limit_value", "deadband")
    return {name: getattr(row, name) for name in columns} | {"valid_from": row.valid_from_unix_s}
