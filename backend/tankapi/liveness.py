"""Whether a stored reading is still live, judged against the server clock (S-083, P1-19).

AGENTS.md section 7: stale data is never shown as live. A reading's quality and
age say how it was sampled (ADR-0008); this module adds whether it is still
current, in one of three states, applied in this order ``[Confirm]``:

1. ``time-unknown``: the scan's wall-clock time was not known (``tk`` false,
   ADR-0004 decision 11), or it is more than ``clock_ahead_s`` ahead of the
   server clock. Its age cannot be measured, so it is never live, and it is a
   different state from a device that has gone quiet (P1-19).
2. ``stale``: a newer value is overdue, because the scan is older than the
   signal's update period plus ``allowance_s`` by the server clock (the device
   is quiet, or its link or the ingest is down); or the device marked the
   reading stale (quality code 1); or its ``age`` is more than ``age_factor``
   update periods, so the device did not refresh it.
3. ``live`` otherwise.

A scan as a whole is judged by step 1 and the first part of step 2, with the
one-second scan period. The quality is never changed: a ``fault``,
``unconfigured`` or ``out-of-range`` reading keeps it, and its liveness says
only whether that report is current. A client shows a live good value only when
the liveness is ``live`` and the quality ``good``. The thresholds are
environment settings with the defaults below; the update periods are the
signal list's.
"""

import os
import re
import time
from dataclasses import dataclass
from enum import Enum

from tankapi.records import Quality, Reading

# interfaces/signals-v1.yaml: the device-health signals every 60 s, every other
# signal every second; a test checks this against the list. A signal not named
# here gets the shortest period, so it turns stale soonest. [Confirm]
UPDATE_RATE_MS = 1000
HEALTH_UPDATE_RATE_MS = 60_000
HEALTH_SIGNAL_IDS = frozenset({9001, 9002, 9003, 9004})
# One consolidated scan record per second (AGENTS.md section 5).
SCAN_PERIOD_MS = 1000
MS_PER_S = 1000

# A batch leaves the device every 5 s (AGENTS.md section 6), so a healthy newest
# scan is about 5 s old on arrival. 14 s more than the period (15 s for a scan)
# allows one late batch and still shows the flag within P1-19's 30 s with a 5 s
# poll. [Confirm] P1-19's open question on the threshold.
ALLOWANCE_S = 14
# One missed sample is tolerated; two are stale. [Confirm]
AGE_FACTOR = 2
# Device and server both keep time by NTP, so a scan more than this far ahead of
# the server clock has a time that cannot be trusted. [Confirm]
CLOCK_AHEAD_S = 2

ALLOWANCE_VARIABLE = "TANKAPI_STALE_ALLOWANCE_S"
AGE_FACTOR_VARIABLE = "TANKAPI_STALE_AGE_FACTOR"
CLOCK_AHEAD_VARIABLE = "TANKAPI_CLOCK_AHEAD_S"
# ASCII digits only, so "٣" or "1.5" is refused rather than read.
WHOLE_NUMBER = re.compile(r"[0-9]{1,6}")


class Liveness(str, Enum):
    """Whether a reading is current, as the API names it."""

    LIVE = "live"
    STALE = "stale"
    TIME_UNKNOWN = "time-unknown"


@dataclass(frozen=True)
class StaleRules:
    """The thresholds one judgement uses."""

    allowance_s: int = ALLOWANCE_S
    age_factor: int = AGE_FACTOR
    clock_ahead_s: int = CLOCK_AHEAD_S

    def __post_init__(self) -> None:
        for name in ("allowance_s", "clock_ahead_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.age_factor < 1:
            raise ValueError("age_factor must be at least 1")


def update_rate_ms(signal_id: int) -> int:
    """How often the signal list says a signal appears in a scan."""
    return HEALTH_UPDATE_RATE_MS if signal_id in HEALTH_SIGNAL_IDS else UPDATE_RATE_MS


def get_stale_rules() -> StaleRules:
    """The thresholds from the environment; an unset one keeps its default."""
    return StaleRules(
        allowance_s=_setting(ALLOWANCE_VARIABLE, ALLOWANCE_S),
        age_factor=_setting(AGE_FACTOR_VARIABLE, AGE_FACTOR),
        clock_ahead_s=_setting(CLOCK_AHEAD_VARIABLE, CLOCK_AHEAD_S),
    )


def _setting(name: str, default: int) -> int:
    text = os.environ.get(name)
    if not text:
        return default
    if not WHOLE_NUMBER.fullmatch(text):
        raise ValueError(f"{name} must be a whole number of up to six digits")
    return int(text)


def server_now() -> float:
    """The server clock in Unix seconds; a dependency, so tests can fix it."""
    return time.time()


def scan_liveness(unix_time_s: int | None, now_s: float, rules: StaleRules) -> Liveness:
    """Whether a scan taken at ``unix_time_s`` (``None``: not known) is still the newest due."""
    return _against_clock(unix_time_s, SCAN_PERIOD_MS, now_s, rules)


def reading_liveness(
    unix_time_s: int | None, reading: Reading, now_s: float, rules: StaleRules
) -> Liveness:
    """Whether one reading of a scan taken at ``unix_time_s`` is still current."""
    period_ms = update_rate_ms(reading.signal_id)
    by_clock = _against_clock(unix_time_s, period_ms, now_s, rules)
    if by_clock is not Liveness.LIVE:
        return by_clock
    if reading.quality is Quality.STALE or reading.age_ms > rules.age_factor * period_ms:
        return Liveness.STALE
    return Liveness.LIVE


def _against_clock(
    unix_time_s: int | None, period_ms: int, now_s: float, rules: StaleRules
) -> Liveness:
    if unix_time_s is None or unix_time_s - now_s > rules.clock_ahead_s:
        return Liveness.TIME_UNKNOWN
    if now_s - unix_time_s > period_ms / MS_PER_S + rules.allowance_s:
        return Liveness.STALE
    return Liveness.LIVE
