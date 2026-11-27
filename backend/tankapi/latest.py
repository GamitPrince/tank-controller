"""The newest value of each signal of a device, flagged live or stale (S-084, P1-19).

``GET /v1/devices/{device_id}/latest`` is what a live view polls. It is
read-only: the router has no other method, and nothing here writes to the
database or sends anything to a device.

For each signal it returns the newest reading the caller may see, from the
scans in the ``LOOKBACK_S`` seconds up to the newest timed one, so a signal sent
once a minute is found too. Each carries its quality, age and value as stored
(``tankapi.readings``) and its ``liveness`` against the server clock
(``tankapi.liveness``, S-083): a value that is no longer current comes back
``stale`` or ``time-unknown``, never ``live`` and never dropped ``[Confirm]``.
``device`` says the same of the device as a whole: ``time-unknown`` when its
newest stored scan has no known time (its clock is not yet set, ADR-0004
decision 11), otherwise the state of the newest timed scan the caller may see,
and ``stale`` when there is none. ``server_time`` is the clock they were judged
against.

Scoping follows S-078, narrowed to now ``[Confirm]``: a customer's caller sees a
device only while it is on one of their tanks, and then only scans from the
current stretch of that ownership; any other device answers as an unknown one
does. Service sees every scan. The ``/v1`` router records every service
request in the audit trail (S-080).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from tankapi.auth import Caller, require_caller
from tankapi.db import ReadingRow, ScanRow
from tankapi.liveness import (
    Liveness,
    StaleRules,
    get_stale_rules,
    reading_liveness,
    scan_liveness,
    server_now,
)
from tankapi.readings import (
    HTTP_NOT_FOUND,
    NOT_FOUND,
    QualityName,
    caller_windows,
    within_window,
)
from tankapi.records import DEVICE_ID_MAX_BYTES, Reading
from tankapi.session import get_session

# Two periods of the slowest signal (device health, every 60 s). [Confirm]
LOOKBACK_S = 120
LIVENESS_HELP = (
    "`live` only while current by the server clock; `stale` when a newer value is "
    "overdue or the device marked it stale; `time-unknown` when its scan's time is "
    "not known. Show a value as live and good only when this is `live` and `quality` is `good`."
)


class LatestValue(BaseModel):
    """The newest reading of one signal; ``value`` is null exactly when the quality has none."""

    signal_id: int
    t: int
    boot_id: str
    sequence: int
    signal_list_version: int
    quality: QualityName
    age_ms: int
    value: int | bool | None
    liveness: Liveness = Field(description=LIVENESS_HELP)


class Latest(BaseModel):
    """What the latest-values endpoint returns."""

    device_id: str
    server_time: float = Field(description="Unix seconds that liveness was judged against.")
    device: Liveness = Field(description="Whether the device's newest scan is current.")
    last_t: int | None = Field(description="The newest timed scan the caller may see.")
    values: list[LatestValue]


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]
CallerDependency = Annotated[Caller, Depends(require_caller)]


@router.get("/devices/{device_id}/latest")
def get_latest(
    session: SessionDependency,
    caller: CallerDependency,
    now: Annotated[float, Depends(server_now)],
    rules: Annotated[StaleRules, Depends(get_stale_rules)],
    device_id: Annotated[str, Path(min_length=1, max_length=DEVICE_ID_MAX_BYTES)],
) -> Latest:
    """The newest value of each signal the caller may see, each flagged live or not."""
    windows = caller_windows(session, caller, device_id, int(now), int(now) + 1)
    newest_known = session.scalar(
        select(ScanRow.time_known)
        .where(ScanRow.device_id == device_id)
        .order_by(ScanRow.id.desc())
        .limit(1)
    )
    if windows == [] or newest_known is None:
        raise HTTPException(HTTP_NOT_FOUND, NOT_FOUND)
    shown = [] if windows is None else [within_window(ScanRow.unix_time_s, windows[0])]
    last_t = session.scalar(
        select(func.max(ScanRow.unix_time_s)).where(
            ScanRow.device_id == device_id, ScanRow.time_known, *shown
        )
    )
    if not newest_known:
        device = Liveness.TIME_UNKNOWN
    else:
        device = Liveness.STALE if last_t is None else scan_liveness(last_t, now, rules)
    values = [] if last_t is None else _values(session, device_id, last_t, shown, now, rules)
    return Latest(device_id=device_id, server_time=now, device=device, last_t=last_t, values=values)


def _values(
    session: Session,
    device_id: str,
    last_t: int,
    shown: list[ColumnElement[bool]],
    now: float,
    rules: StaleRules,
) -> list[LatestValue]:
    t = ScanRow.unix_time_s
    query = (
        select(ScanRow, ReadingRow)
        .join(ReadingRow, ReadingRow.scan_record_id == ScanRow.id)
        .where(ScanRow.device_id == device_id, ScanRow.time_known, *shown)
        .where(t > last_t - LOOKBACK_S, t <= last_t)
        .order_by(t.desc(), ScanRow.id.desc())
    )
    newest: dict[int, LatestValue] = {}
    for scan, row in session.execute(query):
        reading = row.to_reading()
        if reading.signal_id not in newest:
            newest[reading.signal_id] = _value(scan, reading, now, rules)
    return [newest[signal] for signal in sorted(newest)]


def _value(scan: ScanRow, reading: Reading, now: float, rules: StaleRules) -> LatestValue:
    return LatestValue(
        signal_id=reading.signal_id,
        t=scan.unix_time_s,
        boot_id=scan.boot_id.hex(),
        sequence=scan.sequence,
        signal_list_version=scan.signal_list_version,
        quality=reading.quality.name.lower(),
        age_ms=reading.age_ms,
        value=reading.value,
        liveness=reading_liveness(scan.unix_time_s, reading, now, rules),
    )
