"""Replaying a captured stream, keeping the original timestamps.

ADR-0004 decision 13 asks for "outage replay with original timestamps". There
are two halves to that, and both are here or next door:

* the device's own outage buffer, which delivers records it held back with the
  timestamps of the scans that produced them (:mod:`tanksim.link`);
* replaying a capture taken earlier, so a cloud or dashboard change can be
  tested against the same bytes again. That is this module.

Replay never restamps a record. The record's ``up``, ``tk`` and ``t`` fields
are what the device wrote, and a replayed record is byte-identical to the
captured one; only :attr:`tanksim.link.Delivery.replayed` says it came from a
capture. A consumer that stamps arrival time instead of reading the record
would show old data as live, which AGENTS.md section 7 forbids, and replaying a
capture is how you catch that.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cddl import Schema
from .framing import decode_frame, split_frames
from .link import Delivery, Sink
from .record import decode


class ReplayError(ValueError):
    """Raised when a capture cannot be read."""


@dataclass(frozen=True)
class CapturedRecord:
    """One record read back out of a capture."""

    frame: bytes
    sequence: int
    record: dict[str, Any]

    @property
    def uptime_ms(self) -> int:
        """The record's own ``up``, in milliseconds since the device booted."""
        return int(self.record["up"])

    @property
    def unix_time_s(self) -> int | None:
        """The record's own ``t``, or ``None`` when time was not yet known."""
        value = self.record.get("t")
        return None if value is None else int(value)


def read_capture(data: bytes, schema: Schema | None = None) -> list[CapturedRecord]:
    """Decode every frame in a captured byte stream.

    Each frame's CRC is checked and each record is validated against the CDDL
    schema, so a capture that does not match the contract fails here rather
    than confusing whatever is being tested with it.
    """
    captured: list[CapturedRecord] = []
    for index, raw in enumerate(split_frames(data)):
        frame = decode_frame(raw)
        try:
            record = decode(frame.payload, schema)
        except ValueError as error:
            raise ReplayError(
                f"frame {index} of the capture does not match the schema: {error}"
            ) from error
        captured.append(
            CapturedRecord(
                frame=raw + b"\x00",
                sequence=frame.sequence,
                record=record,
            )
        )
    if not captured:
        raise ReplayError("the capture holds no frames")
    return captured


def load_capture(path: Path, schema: Schema | None = None) -> list[CapturedRecord]:
    """Read a capture file written by the simulator."""
    try:
        return read_capture(path.read_bytes(), schema)
    except FileNotFoundError:
        raise ReplayError(f"capture file {path} not found") from None


def replay(captured: list[CapturedRecord], sink: Sink) -> int:
    """Deliver captured records to ``sink`` in order, timestamps untouched.

    Returns how many records were delivered.
    """
    for item in captured:
        sink.deliver(
            Delivery(
                frame=item.frame,
                uptime_ms=item.uptime_ms,
                unix_time_s=item.unix_time_s,
                replayed=True,
            )
        )
    return len(captured)
