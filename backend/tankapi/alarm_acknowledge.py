"""Acknowledging one raised advisory alarm (S-092, P1-18).

``POST /v1/alarms/{event_id}/acknowledgement`` with ``{"note": <optional text>}``
adds one ``alarm_acknowledgements`` row: the event, the caller's token ``sub``
and role, the server's time in Unix milliseconds and the note. The time never
comes from the client. An acknowledgement is a record for people only: it never
sends anything to a device, and it never clears, silences or changes how an
alarm is judged; the evaluator (S-088, S-090) does not read the table. These
alarms are advisory, never trips or interlocks (AGENTS.md section 1).

A customer's operator, maintenance or admin may acknowledge an alarm of their
own customer's tank; service is refused ``[Confirm]``, and the router's audit
records the attempt (S-080). Another customer's event answers exactly as an
unknown one does (S-078). Only a raise still in force can be acknowledged: a
``high`` or ``low`` event with no later judged event of its threshold, since a
later ``cannot_evaluate`` never clears a raise (S-088). "Later" is by scan time,
then recording order, as in S-091. An event is acknowledged at most once; the
table's unique key decides a race. The note is never logged.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.alarm_history import tank_visible
from tankapi.alarm_rules import AlarmState
from tankapi.auth import Caller, Role, require_caller
from tankapi.db import NOTE_MAX_CHARS, AlarmAcknowledgementRow, AlarmEventRow, AlarmThresholdRow
from tankapi.readings import HTTP_NOT_FOUND, NOT_FOUND
from tankapi.session import get_session

ACKNOWLEDGING_ROLES = frozenset({Role.OPERATOR, Role.MAINTENANCE, Role.ADMIN})
RAISED = frozenset({AlarmState.HIGH, AlarmState.LOW})
HTTP_CREATED = 201
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
NOT_ALLOWED = "not allowed"
NOT_RAISED = "alarm not raised"
ALREADY = "already acknowledged"
NS_PER_MS = 1_000_000


class AcknowledgementRequest(BaseModel):
    """The body: an optional note and nothing else."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, min_length=1, max_length=NOTE_MAX_CHARS)


class Acknowledgement(BaseModel):
    """One recorded acknowledgement; ``at`` is the server's Unix time in milliseconds."""

    event_id: int
    subject: str
    role: Role
    at: int
    note: str | None


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]
CallerDependency = Annotated[Caller, Depends(require_caller)]


@router.post("/alarms/{event_id}/acknowledgement", status_code=HTTP_CREATED)
def acknowledge(
    session: SessionDependency,
    caller: CallerDependency,
    event_id: Annotated[int, Path(ge=1)],
    body: AcknowledgementRequest,
) -> Acknowledgement:
    """Records that the caller has seen this raised alarm; 409 if not raised or done."""
    if caller.role not in ACKNOWLEDGING_ROLES:
        raise HTTPException(HTTP_FORBIDDEN, NOT_ALLOWED)
    found = session.execute(
        select(AlarmEventRow, AlarmThresholdRow.tank_id)
        .join(AlarmThresholdRow, AlarmThresholdRow.id == AlarmEventRow.threshold_id)
        .where(AlarmEventRow.id == event_id)
    ).first()
    if found is None or not tank_visible(session, caller, found.tank_id):
        raise HTTPException(HTTP_NOT_FOUND, NOT_FOUND)
    if not _in_force(session, found.AlarmEventRow):
        raise HTTPException(HTTP_CONFLICT, NOT_RAISED)
    row = AlarmAcknowledgementRow(
        alarm_event_id=event_id,
        subject=caller.subject,
        role=caller.role.value,
        at_unix_ms=time.time_ns() // NS_PER_MS,
        note=body.note,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(HTTP_CONFLICT, ALREADY) from None
    return Acknowledgement(
        event_id=event_id, subject=row.subject, role=caller.role, at=row.at_unix_ms, note=row.note
    )


def _in_force(session: Session, event: AlarmEventRow) -> bool:
    """Whether the event is a raise that no later judged event of its threshold replaced."""
    if event.state not in RAISED:
        return False
    t = AlarmEventRow.unix_time_s
    later = or_(t > event.unix_time_s, and_(t == event.unix_time_s, AlarmEventRow.id > event.id))
    replaced = select(AlarmEventRow.id).where(
        AlarmEventRow.threshold_id == event.threshold_id,
        AlarmEventRow.state != AlarmState.CANNOT_EVALUATE,
        later,
    )
    return session.scalar(replaced.limit(1)) is None
