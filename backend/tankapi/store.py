"""Storing the records of one decoded MQTT message (S-070).

:func:`store_message` writes what :func:`tankapi.records.decode_message`
returned for one message, in one transaction: every new record of the message,
or, if any write fails, none of them. MQTT QoS 1 delivers at least once and the
device replays its backlog after an outage (ADR-0004 decisions 7 and 8), so a
record that is already stored is normal traffic. It is skipped, never
overwritten and never an error.

- A scan record is already stored when its device, boot ID and sequence are
  (the unique key of ``scan_records``, S-068).
- A gap record is already stored when a stored gap matches it in every field.
  ``[Confirm]`` Every dropped scan is counted in exactly one gap (S-040), so two
  different gaps cannot agree in all of them; a gap carried forward keeps its
  ``first`` mark but not its ``last`` or ``lost``, so it is stored.

A new scan whose time is known also gets its per-second samples (S-100), in the
same transaction, so a skipped duplicate never adds samples twice.

Exactly what was decoded is stored: the device's own uptime and time, never the
time of arrival, and a faulted reading without a value. Nothing is added
between records; a gap stays a gap (S-040).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from tankapi.db import GapRow, SampleRow, ScanRow
from tankapi.records import GapRecord, Message, ScanRecord

NewScans = Callable[[Session, Sequence[ScanRow]], object]


@dataclass(frozen=True)
class StoreResult:
    """How many records of a message were written, and how many were already stored."""

    stored: int
    skipped: int


def store_message(
    session: Session, records: Sequence[Message], then: NewScans | None = None
) -> StoreResult:
    """Write the records of one message, oldest first, skipping those already stored.

    The session must have no transaction open: this function begins one and
    commits it, or rolls it back and re-raises if any write fails. ``then`` is
    called in the same transaction with the scans that were new (S-090), so
    what it writes is committed with them or not at all.
    """
    new_scans: list[ScanRow] = []
    stored = 0
    with session.begin():
        for record in records:
            # The session flushes before each lookup, so a duplicate inside the
            # same message is found as well as one stored earlier.
            if _already_stored(session, record):
                continue
            row = _row(record)
            session.add(row)
            if isinstance(row, ScanRow):
                new_scans.append(row)
            stored += 1
        if then is not None and new_scans:
            session.flush()
            then(session, new_scans)
    return StoreResult(stored=stored, skipped=len(records) - stored)


def _row(record: Message) -> ScanRow | GapRow:
    if isinstance(record, ScanRecord):
        row = ScanRow.from_record(record)
        row.samples = SampleRow.for_scan(record)
        return row
    return GapRow.from_record(record)


def _already_stored(session: Session, record: Message) -> bool:
    if isinstance(record, ScanRecord):
        query = select(ScanRow.id).where(
            ScanRow.device_id == record.device_id,
            ScanRow.boot_id == record.boot_id,
            ScanRow.sequence == record.sequence,
        )
    else:
        query = select(GapRow.id).where(*_same_gap(record))
    return session.scalars(query.limit(1)).first() is not None


def _same_gap(record: GapRecord) -> list[ColumnElement[bool]]:
    """Every column of the gap equal; a missing Unix time compares as IS NULL."""
    candidate = GapRow.from_record(record)
    columns = (column for column in GapRow.__table__.columns if not column.primary_key)
    return [column == getattr(candidate, column.key) for column in columns]
