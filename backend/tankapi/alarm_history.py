"""Reading one tank's advisory alarm history back (S-091, P1-18).

``GET /v1/tanks/{tank_id}/alarms?from=<t>&to=<t>&limit=<n>`` returns the
``alarm_events`` rows (S-089) that ingest recorded for the tank's thresholds
(S-090) whose scan time ``t`` (Unix seconds, UTC) is in ``[from, to)``, newest
first ``[Confirm]``, at most ``limit`` of them; ``more`` says whether older ones
in the range were left out. It is read-only: the router has no other method, and
nothing here writes to the database or sends anything to a device. These alarms
are reports for people, never trips or interlocks (AGENTS.md section 1).

Each event carries what S-089 stored: the threshold row in force with its limit
and deadband, the value judged and the reading's quality, or the reason it could
not be judged. A ``cannot_evaluate`` event has no value, never a substitute.

An event from a scan whose time was not known has no ``t``, so it cannot be
placed in a range. It is never stamped with its arrival time: it is left out and
counted in ``untimed`` ``[Confirm]``.

Scoping follows S-078 for a tank: a service caller sees every tank, and any
other caller only the tanks of their own customer. Another customer's tank
answers exactly as an unknown one does, so IDs cannot be probed. A tank's
events are all its own, because each was judged against that tank's thresholds
at the scan's time (S-090). Every service request is recorded in the audit
trail with the tank ID (S-080).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from tankapi.alarm_rules import AlarmClass, AlarmState, Direction, Measure, Unavailable
from tankapi.auth import Caller, Role, require_caller
from tankapi.db import AlarmEventRow, AlarmThresholdRow, PlantRow, TankRow
from tankapi.readings import HTTP_NOT_FOUND, HTTP_UNPROCESSABLE, NOT_FOUND, QualityName
from tankapi.records import Quality
from tankapi.session import get_session

# Thirty-one days per request: a month's alarm list in one call. [Confirm]
MAX_RANGE_S = 31 * 86_400
MAX_EVENTS = 1000


class AlarmEvent(BaseModel):
    """One change of an alarm's state; ``value`` is null exactly when ``reason`` is set."""

    id: int
    t: int
    threshold_id: int
    measure: Measure
    signal_id: int
    direction: Direction
    alarm_class: AlarmClass
    limit: int
    deadband: int
    state: AlarmState
    reason: Unavailable | None
    value: float | None
    quality: QualityName | None


class AlarmHistory(BaseModel):
    """What the alarm history endpoint returns, newest first."""

    tank_id: int
    start: int = Field(serialization_alias="from")
    end: int = Field(serialization_alias="to")
    events: list[AlarmEvent]
    more: bool
    untimed: int


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]
CallerDependency = Annotated[Caller, Depends(require_caller)]


@router.get("/tanks/{tank_id}/alarms")
def get_alarm_history(
    session: SessionDependency,
    caller: CallerDependency,
    tank_id: Annotated[int, Path(ge=1)],
    start: Annotated[int, Query(alias="from", ge=0, description="Unix seconds, included.")],
    end: Annotated[int, Query(alias="to", ge=0, description="Unix seconds, excluded.")],
    limit: Annotated[int, Query(ge=1, le=MAX_EVENTS)] = MAX_EVENTS,
) -> AlarmHistory:
    """The tank's alarm events in ``[from, to)``, newest first, at most ``limit``."""
    if not start < end <= start + MAX_RANGE_S:
        raise HTTPException(HTTP_UNPROCESSABLE, f"need from < to <= from + {MAX_RANGE_S}")
    if not _visible(session, caller, tank_id):
        raise HTTPException(HTTP_NOT_FOUND, NOT_FOUND)
    t = AlarmEventRow.unix_time_s
    query = (
        _tank_events(tank_id)
        .where(t >= start, t < end)
        .order_by(t.desc(), AlarmEventRow.id.desc())
        .limit(limit + 1)
    )
    rows = session.execute(query).all()
    untimed = select(func.count()).select_from(_tank_events(tank_id).where(t.is_(None)).subquery())
    return AlarmHistory(
        tank_id=tank_id,
        start=start,
        end=end,
        events=[_event(event, threshold) for event, threshold in rows[:limit]],
        more=len(rows) > limit,
        untimed=session.scalar(untimed),
    )


def _visible(session: Session, caller: Caller, tank_id: int) -> bool:
    """Whether the tank exists and, unless the caller is service, is their customer's."""
    query = select(PlantRow.customer_id).join(TankRow, TankRow.plant_id == PlantRow.id)
    owner = session.scalar(query.where(TankRow.id == tank_id))
    if owner is None:
        return False
    return caller.role is Role.SERVICE or owner == caller.customer_id


def _tank_events(tank_id: int) -> Select:
    return (
        select(AlarmEventRow, AlarmThresholdRow)
        .join(AlarmThresholdRow, AlarmThresholdRow.id == AlarmEventRow.threshold_id)
        .where(AlarmThresholdRow.tank_id == tank_id)
    )


def _event(event: AlarmEventRow, threshold: AlarmThresholdRow) -> AlarmEvent:
    quality = None if event.quality is None else Quality(event.quality).name.lower()
    return AlarmEvent(
        id=event.id,
        t=event.unix_time_s,
        threshold_id=threshold.id,
        measure=threshold.measure,
        signal_id=threshold.signal_id,
        direction=threshold.direction,
        alarm_class=threshold.alarm_class,
        limit=event.limit_value,
        deadband=event.deadband,
        state=event.state,
        reason=event.reason,
        value=event.value,
        quality=quality,
    )
