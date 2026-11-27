"""The stale-reading rule against a fixed clock (S-083, P1-19)."""

import re
import time
from pathlib import Path

import pytest

from tankapi.liveness import (
    AGE_FACTOR_VARIABLE,
    ALLOWANCE_VARIABLE,
    CLOCK_AHEAD_VARIABLE,
    Liveness,
    StaleRules,
    get_stale_rules,
    reading_liveness,
    scan_liveness,
    server_now,
    update_rate_ms,
)
from tankapi.records import Quality, Reading

SIGNAL_LIST = Path(__file__).parents[2] / "interfaces" / "signals-v1.yaml"
NOW = 1_795_000_000.0
T = int(NOW)
RULES = StaleRules()
RADAR, UPTIME = 1001, 9001
VALUED = {Quality.GOOD: 12_000, Quality.STALE: 12_000, Quality.OUT_OF_RANGE: 20_500}
VARIABLES = (ALLOWANCE_VARIABLE, AGE_FACTOR_VARIABLE, CLOCK_AHEAD_VARIABLE)


def reading(quality: Quality = Quality.GOOD, age_ms: int = 100, signal: int = RADAR) -> Reading:
    return Reading(signal_id=signal, quality=quality, age_ms=age_ms, value=VALUED.get(quality))


def signal_list_rates() -> dict[int, int]:
    pieces = re.split(r"^\s*- id:\s*(\d+)\s*$", SIGNAL_LIST.read_text(), flags=re.MULTILINE)
    return {
        int(signal): int(re.search(r"^\s+update_rate_ms:\s*(\d+)", body, re.MULTILINE)[1])
        for signal, body in zip(pieces[1::2], pieces[2::2], strict=True)
    }


def test_every_update_rate_is_the_signal_lists() -> None:
    rates = signal_list_rates()
    assert len(rates) == 27
    assert {signal: update_rate_ms(signal) for signal in rates} == rates


def test_a_fresh_good_reading_is_live() -> None:
    assert reading_liveness(T, reading(), NOW, RULES) is Liveness.LIVE


@pytest.mark.parametrize(("seconds", "expected"), [(15, Liveness.LIVE), (15.001, Liveness.STALE)])
def test_a_scan_with_no_newer_one_for_15_s_is_stale(seconds: float, expected: Liveness) -> None:
    assert scan_liveness(T, T + seconds, RULES) is expected
    assert reading_liveness(T, reading(), T + seconds, RULES) is expected


@pytest.mark.parametrize(("seconds", "expected"), [(74, Liveness.LIVE), (74.001, Liveness.STALE)])
def test_a_once_a_minute_signal_is_given_its_own_period(seconds: float, expected: Liveness) -> None:
    assert reading_liveness(T, reading(signal=UPTIME), T + seconds, RULES) is expected


@pytest.mark.parametrize(("age_ms", "expected"), [(2000, Liveness.LIVE), (2001, Liveness.STALE)])
def test_a_reading_older_than_two_update_periods_is_stale(age_ms: int, expected: Liveness) -> None:
    assert reading_liveness(T, reading(age_ms=age_ms), NOW, RULES) is expected


def test_the_devices_own_stale_quality_is_always_stale() -> None:
    assert reading_liveness(T, reading(Quality.STALE, age_ms=0), T, RULES) is Liveness.STALE


@pytest.mark.parametrize("quality", list(Quality))
def test_an_untimed_scan_is_never_live(quality: Quality) -> None:
    assert scan_liveness(None, NOW, RULES) is Liveness.TIME_UNKNOWN
    assert reading_liveness(None, reading(quality), NOW, RULES) is Liveness.TIME_UNKNOWN


@pytest.mark.parametrize(("ahead", "expected"), [(2, Liveness.LIVE), (3, Liveness.TIME_UNKNOWN)])
def test_a_scan_ahead_of_the_server_clock_has_no_trusted_time(
    ahead: int, expected: Liveness
) -> None:
    assert scan_liveness(T + ahead, T, RULES) is expected
    assert reading_liveness(T + ahead, reading(), T, RULES) is expected


@pytest.mark.parametrize("quality", [Quality.OUT_OF_RANGE, Quality.FAULT, Quality.UNCONFIGURED])
def test_a_bad_quality_follows_the_same_time_rule_and_is_left_as_sent(quality: Quality) -> None:
    sent = reading(quality)
    assert reading_liveness(T, sent, NOW, RULES) is Liveness.LIVE
    assert reading_liveness(T, sent, NOW + 16, RULES) is Liveness.STALE
    assert sent == reading(quality)


def test_the_defaults_apply_when_nothing_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(ALLOWANCE_VARIABLE, "")
    assert get_stale_rules() == StaleRules(allowance_s=14, age_factor=2, clock_ahead_s=2)


def test_the_thresholds_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, text in zip(VARIABLES, ("29", "3", "0"), strict=True):
        monkeypatch.setenv(name, text)
    rules = get_stale_rules()
    assert rules == StaleRules(allowance_s=29, age_factor=3, clock_ahead_s=0)
    assert scan_liveness(T, T + 30, rules) is Liveness.LIVE
    assert scan_liveness(T + 1, T, rules) is Liveness.TIME_UNKNOWN
    assert reading_liveness(T, reading(age_ms=3000), T, rules) is Liveness.LIVE


@pytest.mark.parametrize("text", ["abc", "-1", "1.5", "٣", "1234567", " 15"])
def test_a_setting_that_is_not_a_whole_number_is_refused(
    monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    monkeypatch.setenv(AGE_FACTOR_VARIABLE, text)
    with pytest.raises(ValueError, match=AGE_FACTOR_VARIABLE):
        get_stale_rules()


@pytest.mark.parametrize("fields", [{"allowance_s": -1}, {"age_factor": 0}, {"clock_ahead_s": -1}])
def test_a_threshold_out_of_range_is_refused(fields: dict[str, int]) -> None:
    with pytest.raises(ValueError, match=next(iter(fields))):
        StaleRules(**fields)


def test_now_is_the_server_clock() -> None:
    before = time.time()
    assert before <= server_now() <= time.time()
