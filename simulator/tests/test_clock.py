"""Tests for the boot-relative clock of ADR-0004 decision 11."""

from __future__ import annotations

import pytest

from tanksim.clock import ClockError, SimClock

BOOT_UNIX_S = 1763683200


def test_time_is_known_immediately_when_sntp_needs_no_time():
    clock = SimClock(boot_unix_s=BOOT_UNIX_S)
    assert clock.time_known is True
    assert clock.unix_time_s == BOOT_UNIX_S


def test_time_is_not_known_until_sntp_answers():
    clock = SimClock(boot_unix_s=BOOT_UNIX_S, sntp_sync_after_ms=5000)
    assert clock.time_known is False
    assert clock.unix_time_s is None

    clock.advance(4999)
    assert clock.time_known is False

    clock.advance(1)
    assert clock.time_known is True
    assert clock.unix_time_s == BOOT_UNIX_S + 5


def test_uptime_accumulates():
    clock = SimClock(boot_unix_s=BOOT_UNIX_S)
    clock.advance(1500)
    clock.advance(1500)
    assert clock.uptime_ms == 3000
    assert clock.uptime_s == 3


def test_the_clock_cannot_run_backwards():
    clock = SimClock(boot_unix_s=BOOT_UNIX_S)
    with pytest.raises(ClockError, match="cannot advance"):
        clock.advance(-1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"boot_unix_s": -1},
        {"boot_unix_s": BOOT_UNIX_S, "sntp_sync_after_ms": -1},
        {"boot_unix_s": BOOT_UNIX_S, "uptime_ms": -1},
    ],
)
def test_an_impossible_clock_is_refused(kwargs):
    with pytest.raises(ClockError):
        SimClock(**kwargs)
