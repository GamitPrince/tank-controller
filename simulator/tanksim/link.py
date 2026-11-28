"""The link to the cloud, with the outage buffer of ADR-0004 decisions 8 and 12.

Decision 8 is two-tier failover after about ten seconds without a cloud
acknowledgement; decision 12 is a compact append-only log that holds records
while the cloud is unreachable. Decision 13 asks the simulator for outage replay
that keeps the original timestamps.

That last point is the whole reason this module exists. When the link comes
back, the buffered records are delivered **unchanged**: each still carries the
uptime and Unix time of the scan that produced it, not the moment it was
finally sent. A consumer that stamped arrival time instead would silently
compress an outage into a single instant, and would show buffered data as live,
which AGENTS.md section 7 forbids. :class:`Delivery` carries the original
timestamps alongside the frame so a sink can tell the two apart.

The buffer is append-only and finite. When it is full, the record that cannot be
written is dropped and counted; the records already in the log are kept, because
an append-only log does not overwrite its own history.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import BinaryIO, Protocol

#: How many records the outage buffer holds. ``[Confirm]`` The real figure comes
#: from the flash budget in P1-14; this default is a round number that makes an
#: overflow reachable in a test.
DEFAULT_BUFFER_CAPACITY = 1024


class LinkError(ValueError):
    """Raised when the link is configured impossibly."""


@dataclass(frozen=True)
class Delivery:
    """One frame as a sink receives it."""

    frame: bytes
    #: Uptime of the scan that produced the record, in milliseconds.
    uptime_ms: int
    #: Unix time of that scan, or ``None`` if time was not yet known then.
    unix_time_s: int | None
    #: True when the frame sat in the outage buffer before being delivered.
    replayed: bool = False


class Sink(Protocol):
    """Where delivered frames go."""

    def deliver(self, delivery: Delivery) -> None:
        """Accept one delivery."""


class RecordingSink:
    """A sink that keeps every delivery, for tests and for the ``--quiet`` run."""

    def __init__(self) -> None:
        self.deliveries: list[Delivery] = []

    def deliver(self, delivery: Delivery) -> None:
        self.deliveries.append(delivery)

    @property
    def frames(self) -> list[bytes]:
        """Just the frames, in delivery order."""
        return [delivery.frame for delivery in self.deliveries]


class StreamSink:
    """A sink that writes the raw framed bytes to a binary stream.

    This is the simulator's main output: the same byte stream the real link
    carries, so a consumer reads it with the same code either way.
    """

    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    def deliver(self, delivery: Delivery) -> None:
        self._stream.write(delivery.frame)
        self._stream.flush()


class FanOutSink:
    """A sink that hands every delivery to several sinks, in order."""

    def __init__(self, *sinks: Sink) -> None:
        self._sinks = sinks

    def deliver(self, delivery: Delivery) -> None:
        for sink in self._sinks:
            sink.deliver(delivery)


class BufferedLink:
    """A link that buffers while it is down and replays when it comes back."""

    def __init__(self, sink: Sink, capacity: int = DEFAULT_BUFFER_CAPACITY) -> None:
        if capacity < 1:
            raise LinkError(f"buffer capacity must be at least 1, got {capacity}")
        self._sink = sink
        self._capacity = capacity
        self._buffer: deque[Delivery] = deque()
        self._up = True
        self.dropped = 0

    @property
    def up(self) -> bool:
        """Whether the cloud is currently acknowledging publishes."""
        return self._up

    @property
    def capacity(self) -> int:
        """How many records the outage buffer holds."""
        return self._capacity

    @property
    def buffered(self) -> int:
        """How many records are waiting in the outage buffer."""
        return len(self._buffer)

    @property
    def buffer_fraction(self) -> float:
        """Buffer fill as a fraction, which the log-buffer health signal reports."""
        return len(self._buffer) / self._capacity

    def publish(self, frame: bytes, uptime_ms: int, unix_time_s: int | None) -> bool:
        """Send one frame, or buffer it while the link is down.

        Returns whether the frame reached the sink now.
        """
        delivery = Delivery(frame=frame, uptime_ms=uptime_ms, unix_time_s=unix_time_s)
        if self._up:
            self._sink.deliver(delivery)
            return True
        if len(self._buffer) >= self._capacity:
            # An append-only log that is full cannot take the new record. The
            # history already written is what survives.
            self.dropped += 1
            return False
        self._buffer.append(delivery)
        return False

    def set_up(self, up: bool) -> int:
        """Bring the link up or down. Returns how many records were replayed.

        Coming up flushes the buffer in order, each record keeping the
        timestamps of the scan that produced it.
        """
        was_up = self._up
        self._up = up
        if up and not was_up:
            return self._flush()
        return 0

    def _flush(self) -> int:
        replayed = 0
        while self._buffer:
            delivery = self._buffer.popleft()
            self._sink.deliver(
                Delivery(
                    frame=delivery.frame,
                    uptime_ms=delivery.uptime_ms,
                    unix_time_s=delivery.unix_time_s,
                    replayed=True,
                )
            )
            replayed += 1
        return replayed
