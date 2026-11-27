"""The audit trail of service staff's ``/v1`` requests (S-080).

ADR-0008 decision 3: service is our own staff, may read any customer's data,
and every such access is recorded; decision 4 makes the record an append-only
table, ``audit_entries`` (migration 0004 refuses UPDATE and DELETE). Two pieces
do it. :func:`noting_requests` gives the ``/v1`` router a dependency that runs
once the token has passed and, for a service caller, keeps who asked, what
(method, route template, device ID and the query parameters that select data)
and when. :func:`write_entries`, an HTTP middleware, adds the response status
and writes the entry after the response is built and before it is sent, so a
refused request (404, 422, 500) is recorded too. A request refused before the
caller is known (401, 403, 503) has no service caller to record.

Fail closed ``[Confirm]``: when the entry cannot be written, the response is
dropped and the caller gets 503, so no service read goes unrecorded. Customer
callers are not recorded ``[Confirm]``: ADR-0008 asks only for service.

Never recorded: the token, any header, a query parameter not in
:data:`SELECTING_PARAMETERS` (it could hold anything, a token included) and any
reading. Nothing reads the table yet, and nothing here talks to a device.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from tankapi.auth import Caller, Role, require_caller
from tankapi.db import AuditRow
from tankapi.session import get_engine

AUDITED_ROLES = frozenset({Role.SERVICE})
# The query parameters that choose which data a request reads.
SELECTING_PARAMETERS = ("signal", "from", "to")
DEVICE_PARAMETER = "device_id"
# A refused request may carry anything, so each recorded value is cut to this.
VALUE_MAX_CHARS = 64
NS_PER_MS = 1_000_000
HTTP_SERVER_ERROR = 500
HTTP_UNAVAILABLE = 503
NOT_AVAILABLE = {"detail": "not available"}

log = logging.getLogger(__name__)


def noting_requests(prefix: str) -> Callable[..., None]:
    """The dependency for the router at ``prefix`` that keeps a service caller's request."""

    def note(
        request: Request,
        caller: Annotated[Caller, Depends(require_caller)],
        engine: Annotated[Engine, Depends(get_engine)],
    ) -> None:
        if caller.role not in AUDITED_ROLES:
            return
        query = request.query_params
        selection = {name: _cut(query[name]) for name in SELECTING_PARAMETERS if name in query}
        device_id = request.path_params.get(DEVICE_PARAMETER)
        entry = AuditRow(
            at_unix_ms=time.time_ns() // NS_PER_MS,
            subject=caller.subject,
            role=caller.role.value,
            method=request.method,
            # FastAPI puts the route as declared, without the router's prefix, in the scope.
            route=prefix + request.scope["route"].path,
            device_id=None if device_id is None else _cut(device_id),
            query=json.dumps(selection, sort_keys=True),
        )
        request.state.audit_entry = (entry, engine)

    return note


async def write_entries(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Writes the kept entry with the response's status; 503 instead when it cannot."""
    try:
        response = await call_next(request)
    except Exception:
        await run_in_threadpool(_write, request, HTTP_SERVER_ERROR)
        raise
    if await run_in_threadpool(_write, request, response.status_code):
        return response
    return JSONResponse(NOT_AVAILABLE, status_code=HTTP_UNAVAILABLE)


def _write(request: Request, status: int) -> bool:
    """Writes the request's entry if it has one; ``False`` only when the write failed."""
    kept: tuple[AuditRow, Engine] | None = getattr(request.state, "audit_entry", None)
    if kept is None:
        return True
    entry, engine = kept
    entry.status = status
    try:
        with Session(engine) as db:
            db.add(entry)
            db.commit()
    except SQLAlchemyError as error:
        # The class only: the error's text repeats the statement and its values.
        log.error(
            "audit entry of %s on %s not written: %s",
            entry.subject,
            entry.route,
            type(error).__name__,
        )
        return False
    return True


def _cut(value: str) -> str:
    return value[:VALUE_MAX_CHARS]
