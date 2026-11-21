"""The simulated clock, following ADR-0004 decision 11.

Decision 11: time is SNTP where available, otherwise boot-relative, with a boot
id and a "time not yet known" flag. A real device boots without knowing the
wall clock, publishes records that carry only an uptime, and gains a Unix time
once SNTP answers; records buffered before that are placed on a timeline later
using the boot id.

The clock is advanced explicitly rather than read from the host, so a test can
cover a whole outage in microseconds and two runs with the same arguments
produce the same records.
"""

from __future__ import annotations

from dataclasses import dataclass


class ClockError(ValueError):
    """Raised when the clock is configured or advanced impossibly."""


@dataclass
class SimClock:
    """A deterministic boot-relative clock that learns the wall clock later."""

    boot_unix_s: int
    sntp_sync_after_ms: int = 0
    uptime_ms: int = 0

    def __post_init__(self) -> None:
        if self.boot_unix_s < 0:
            raise ClockError("boot_unix_s must not be negative")
        if self.sntp_sync_after_ms < 0:
            raise ClockError("sntp_sync_after_ms must not be negative")
        if self.uptime_ms < 0:
            raise ClockError("uptime_ms must not be negative")

    def advance(self, milliseconds: int) -> None:
        """Move the clock forward. Time never runs backwards on a device."""
        if milliseconds < 0:
            raise ClockError(f"cannot advance the clock by {milliseconds} ms")
        self.uptime_ms += milliseconds

    @property
    def time_known(self) -> bool:
        """The record's ``tk`` flag: true once SNTP has answered."""
        return self.uptime_ms >= self.sntp_sync_after_ms

    @property
    def unix_time_s(self) -> int | None:
        """The record's ``t`` field, or ``None`` while time is not yet known."""
        if not self.time_known:
            return None
        return self.boot_unix_s + self.uptime_ms // 1000

    @property
    def uptime_s(self) -> int:
        """Whole seconds since boot, the basis of boot-relative time."""
        return self.uptime_ms // 1000
