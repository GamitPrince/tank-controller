"""Reading one device's stored readings back, by signal and time range (S-072).

``GET /v1/devices/{device_id}/readings?signal=<id>&from=<t>&to=<t>`` returns
the stored readings of one signal whose scan time ``t`` (Unix seconds, UTC) is
in ``[from, to)``, oldest first. It is read-only: the router has no other
method, and nothing here writes to the database or sends anything to a device.

Every point carries its quality and age exactly as the device sent them, and a
faulted or unconfigured reading comes back with no value, never a substitute
(AGENTS.md section 7). Values are the stored scaled integers or bools, with the
signal-list version each was sent under; the client applies the signal's
``scale`` from that list. ``[Confirm]``

A scan whose wall-clock time was not known (``tk`` false) has no ``t``, so it
cannot be placed in a range. It is never stamped with its arrival time: it is
left out and counted in ``untimed``. ``[Confirm]``

Gaps are returned as gaps, and nothing is filled in across one (S-040). A gap
is returned when it overlaps the range or may overlap it: an end whose time
was not known is treated as open. A gap with neither time known is counted in
``untimed`` instead.

The router has no prefix of its own: ``tankapi.main`` mounts it under ``/v1``,
behind the token check (S-075). ``[Confirm]`` There is no per-customer scoping
yet, so any valid token reads any device: this endpoint runs locally only and
must not be deployed before the scoping story (ADR-0008: the backend checks
every request).
"""

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session

from tankapi.db import GapRow, ReadingRow, ScanRow
from tankapi.records import DEVICE_ID_MAX_BYTES, GapRecord, LostScan, Quality
from tankapi.session import get_session

# One hour of one-second scans per request; longer trends will read per-minute
# summaries (ADR-0007), a later story. [Confirm]
MAX_RANGE_S = 3600
MAX_POINTS = 3600
HTTP_UNPROCESSABLE = 422
HTTP_NOT_FOUND = 404

QualityName = Enum("QualityName", [(q.name, q.name.lower()) for q in Quality], type=str)


class Point(BaseModel):
    """One stored reading. ``value`` is null exactly when the quality has none."""

    t: int
    boot_id: str
    sequence: int
    signal_list_version: int
    quality: QualityName
    age_ms: int
    value: int | bool | None


class GapMark(BaseModel):
    """Where the first or last dropped scan of a gap sat; ``t`` is null when not known."""

    boot_id: str
    sequence: int
    t: int | None


class Gap(BaseModel):
    """``lost`` scans from ``first`` to ``last`` that will never arrive."""

    lost: int
    first: GapMark
    last: GapMark


class Untimed(BaseModel):
    """What this device stored with no wall-clock time, so outside every range."""

    points: int
    gaps: int


class Readings(BaseModel):
    """What the readings endpoint returns."""

    device_id: str
    signal_id: int
    start: int = Field(serialization_alias="from")
    end: int = Field(serialization_alias="to")
    points: list[Point]
    gaps: list[Gap]
    untimed: Untimed


router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/devices/{device_id}/readings")
def get_readings(
    session: SessionDependency,
    device_id: Annotated[str, Path(min_length=1, max_length=DEVICE_ID_MAX_BYTES)],
    signal: Annotated[int, Query(ge=0, description="The signal `id` from the signal list.")],
    start: Annotated[int, Query(alias="from", ge=0, description="Unix seconds, included.")],
    end: Annotated[int, Query(alias="to", ge=0, description="Unix seconds, excluded.")],
) -> Readings:
    """One signal's stored readings in ``[from, to)``, with the gaps that overlap it."""
    if not start < end <= start + MAX_RANGE_S:
        raise HTTPException(HTTP_UNPROCESSABLE, f"need from < to <= from + {MAX_RANGE_S}")
    if not _device_known(session, device_id):
        raise HTTPException(HTTP_NOT_FOUND, f"no records stored for device {device_id!r}")
    points = _points(session, device_id, signal, start, end)
    if len(points) > MAX_POINTS:
        raise HTTPException(HTTP_UNPROCESSABLE, f"more than {MAX_POINTS} points; narrow the range")
    untimed = Untimed(
        points=_untimed_points(session, device_id, signal), gaps=_untimed_gaps(session, device_id)
    )
    return Readings(
        device_id=device_id,
        signal_id=signal,
        start=start,
        end=end,
        points=points,
        gaps=_gaps(session, device_id, start, end),
        untimed=untimed,
    )


def _device_known(session: Session, device_id: str) -> bool:
    scans = exists().where(ScanRow.device_id == device_id)
    gaps = exists().where(GapRow.device_id == device_id)
    return bool(session.scalar(select(or_(scans, gaps))))


def _signal_scans(device_id: str, signal_id: int) -> Select:
    return (
        select(ScanRow, ReadingRow)
        .join(ReadingRow, ReadingRow.scan_record_id == ScanRow.id)
        .where(ScanRow.device_id == device_id, ReadingRow.signal_id == signal_id)
    )


def _points(session: Session, device_id: str, signal_id: int, start: int, end: int) -> list[Point]:
    query = (
        _signal_scans(device_id, signal_id)
        .where(ScanRow.time_known, ScanRow.unix_time_s >= start, ScanRow.unix_time_s < end)
        .order_by(ScanRow.unix_time_s, ScanRow.boot_id, ScanRow.sequence)
        .limit(MAX_POINTS + 1)
    )
    return [_point(scan, reading) for scan, reading in session.execute(query)]


def _point(scan: ScanRow, row: ReadingRow) -> Point:
    reading = row.to_reading()
    return Point(
        t=scan.unix_time_s,
        boot_id=scan.boot_id.hex(),
        sequence=scan.sequence,
        signal_list_version=scan.signal_list_version,
        quality=reading.quality.name.lower(),
        age_ms=reading.age_ms,
        value=reading.value,
    )


def _untimed_points(session: Session, device_id: str, signal_id: int) -> int:
    query = _signal_scans(device_id, signal_id).where(~ScanRow.time_known).subquery()
    return session.scalar(select(func.count()).select_from(query))


def _untimed_gaps(session: Session, device_id: str) -> int:
    query = (
        select(func.count())
        .select_from(GapRow)
        .where(
            GapRow.device_id == device_id,
            GapRow.first_unix_time_s.is_(None),
            GapRow.last_unix_time_s.is_(None),
        )
    )
    return session.scalar(query)


def _gaps(session: Session, device_id: str, start: int, end: int) -> list[Gap]:
    first, last = GapRow.first_unix_time_s, GapRow.last_unix_time_s
    query = (
        select(GapRow)
        .where(GapRow.device_id == device_id)
        .where(or_(first.is_not(None), last.is_not(None)))
        .where(or_(first.is_(None), first < end), or_(last.is_(None), last >= start))
        .order_by(GapRow.id)
    )
    return [_gap(row.to_record()) for row in session.scalars(query)]


def _gap(record: GapRecord) -> Gap:
    def mark(lost_scan: LostScan) -> GapMark:
        return GapMark(
            boot_id=lost_scan.boot_id.hex(), sequence=lost_scan.sequence, t=lost_scan.unix_time_s
        )

    return Gap(lost=record.lost, first=mark(record.first), last=mark(record.last))
