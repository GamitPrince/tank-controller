"""The gap record for scans the outage buffer had to drop (S-040).

When the buffer is full, a scan that cannot be written is lost. Without a gap
record the cloud would see a silent hole, which a trend shows as "nothing
happened". :func:`gap_frame` builds that record from the first and last
dropped frames, so the time fields are exactly the ones those scans carried.
"""

from __future__ import annotations

from typing import Any

import cbor2

from .cddl import Schema
from .framing import decode_frame, encode_frame
from .record import RECORD_SCHEMA_VERSION, decode, default_schema

#: The time fields a lost scan keeps, from `lost-scan` in records.cddl.
_LOST_SCAN_KEYS = ("boot", "seq", "up", "tk", "t")


def _lost_scan(record: dict[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in _LOST_SCAN_KEYS if key in record}


def gap_frame(first: bytes, last: bytes, lost: int, schema: Schema | None = None) -> bytes:
    """A framed gap record counting ``lost`` scans from ``first`` to ``last``.

    The frame reuses the sequence number of the last dropped
    scan, which was never sent, so the next live frame still follows it.
    """
    schema = schema or default_schema()
    last_frame = decode_frame(last)
    oldest = decode(decode_frame(first).payload, schema)
    newest = decode(last_frame.payload, schema)
    record = {
        "v": RECORD_SCHEMA_VERSION,
        "dev": oldest["dev"],
        "gap": {"lost": lost, "first": _lost_scan(oldest), "last": _lost_scan(newest)},
    }
    schema.validate(record, "gap-record")
    return encode_frame(last_frame.sequence, cbor2.dumps(record))
