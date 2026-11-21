"""Tests for tanksim.scaling.

Covers the cases AGENTS.md section 7 requires: out-of-range values and invalid
configuration, not just the happy path.
"""

from __future__ import annotations

import pytest

from tanksim import __version__
from tanksim.scaling import SpanError, scale_linear

# A 4-20 mA input mapped onto a 0-100 percent level, as the AD4111 channels are.
RAW_LOW = 4.0
RAW_HIGH = 20.0
ENG_LOW = 0.0
ENG_HIGH = 100.0


def scale(raw: float):
    return scale_linear(raw, RAW_LOW, RAW_HIGH, ENG_LOW, ENG_HIGH)


def test_version_is_a_string():
    assert isinstance(__version__, str)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(4.0, 0.0), (12.0, 50.0), (20.0, 100.0), (8.0, 25.0)],
)
def test_scales_within_span(raw: float, expected: float):
    reading = scale(raw)
    assert reading.value == pytest.approx(expected)
    assert reading.in_range is True


def test_span_ends_count_as_in_range():
    assert scale(RAW_LOW).in_range is True
    assert scale(RAW_HIGH).in_range is True


@pytest.mark.parametrize("raw", [3.9, 0.0, -1.0, 20.1, 25.0])
def test_flags_out_of_range_without_clamping(raw: float):
    reading = scale(raw)
    assert reading.in_range is False
    # Extrapolated, not clamped: a caller can see how far out the reading is.
    assert reading.value < ENG_LOW or reading.value > ENG_HIGH


def test_below_span_extrapolates_negative():
    assert scale(2.0).value == pytest.approx(-12.5)


def test_above_span_extrapolates_above_full():
    assert scale(22.0).value == pytest.approx(112.5)


@pytest.mark.parametrize(
    ("raw_low", "raw_high"),
    [(20.0, 4.0), (4.0, 4.0)],
)
def test_rejects_bad_raw_span(raw_low: float, raw_high: float):
    with pytest.raises(SpanError, match="raw span"):
        scale_linear(10.0, raw_low, raw_high, ENG_LOW, ENG_HIGH)


def test_rejects_bad_engineering_span():
    with pytest.raises(SpanError, match="engineering span"):
        scale_linear(10.0, RAW_LOW, RAW_HIGH, ENG_HIGH, ENG_LOW)


def test_reading_is_immutable():
    reading = scale(12.0)
    with pytest.raises(AttributeError):
        reading.value = 1.0  # type: ignore[misc]
