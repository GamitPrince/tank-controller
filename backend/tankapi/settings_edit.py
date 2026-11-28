"""What every edit of a tank's settings shares: who may edit, and the change log (S-102).

A tank's alarm thresholds (S-087) and level configuration (S-085) are cloud
settings for advisory alarms and the level display; they are never sent to a
device. The customer's admin may change their own customer's tanks, and service
any tank; operator and maintenance read only (S-101 [Confirm] 1). Another
customer's tank answers exactly as an unknown one does (S-078).

A change never rewrites the past (S-101 [Confirm] 2): it closes the row in force
at the server's second and opens the next from that second, so a scan is still
judged by the setting of its own time. A second change to one row in the same
second is refused with 409. Each change adds one ``config_changes`` row (S-101)
in the same transaction, so no change is ever stored unrecorded.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from tankapi.alarm_history import tank_visible
from tankapi.auth import Caller, Role
from tankapi.db import ConfigChangeRow
from tankapi.readings import HTTP_NOT_FOUND, NOT_FOUND

EDITING_ROLES = frozenset({Role.ADMIN, Role.SERVICE})
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
NOT_ALLOWED = "not allowed"
TOO_SOON = "changed less than a second ago; try again"
NS_PER_MS = 1_000_000
MS_PER_S = 1_000


def now_ms() -> int:
    """The server's time in Unix milliseconds; a change never takes the client's."""
    return time.time_ns() // NS_PER_MS


def require_editor(session: Session, caller: Caller, tank_id: int) -> None:
    """403 unless the caller may edit, then 404 unless the tank is theirs to see."""
    if caller.role not in EDITING_ROLES:
        raise HTTPException(HTTP_FORBIDDEN, NOT_ALLOWED)
    if not tank_visible(session, caller, tank_id):
        raise HTTPException(HTTP_NOT_FOUND, NOT_FOUND)


def refuse(reason: str) -> HTTPException:
    """A change that breaks a rule the request body alone cannot show."""
    return HTTPException(HTTP_UNPROCESSABLE, reason)


def too_soon() -> HTTPException:
    return HTTPException(HTTP_CONFLICT, TOO_SOON)


def record_change(
    session: Session,
    caller: Caller,
    at_ms: int,
    tank_id: int,
    kind: str,
    before: tuple[int, dict[str, Any]] | None,
    after: tuple[int, dict[str, Any]],
) -> None:
    """Adds the change's log row; ``before`` and ``after`` are a row ID and its values."""
    session.add(
        ConfigChangeRow(
            at_unix_ms=at_ms,
            subject=caller.subject,
            role=caller.role.value,
            tank_id=tank_id,
            kind=kind,
            before_row_id=None if before is None else before[0],
            before=None if before is None else _json(before[1]),
            after_row_id=after[0],
            after=_json(after[1]),
        )
    )


def _json(values: dict[str, Any]) -> str:
    return json.dumps(values, sort_keys=True)
