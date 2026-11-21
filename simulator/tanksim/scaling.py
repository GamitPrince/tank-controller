"""Linear scaling between a raw transducer reading and an engineering value.

Used for the 4-20 mA inputs on the AD4111 (ADR-0002: channel 1 radar level,
channel 2 pressure level). The scale factors themselves come from the signal
list in ``interfaces/`` once story P1-03 defines it; nothing is hardcoded here.

A reading outside the raw span is a fault, not a value to clamp silently:
AGENTS.md section 7 requires failed sensors to be flagged and excluded, never
replaced. ``scale_linear`` therefore reports out-of-range separately from the
scaled number and leaves the decision to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass


class SpanError(ValueError):
    """Raised when a raw or engineering span is zero or inverted."""


@dataclass(frozen=True)
class ScaledReading:
    """A scaled value and whether its raw input sat inside the raw span."""

    value: float
    in_range: bool


def _check_span(low: float, high: float, name: str) -> None:
    if high <= low:
        raise SpanError(f"{name} span must have high greater than low, got {low} to {high}")


def scale_linear(
    raw: float,
    raw_low: float,
    raw_high: float,
    eng_low: float,
    eng_high: float,
) -> ScaledReading:
    """Map ``raw`` from the raw span onto the engineering span.

    The value is extrapolated beyond the raw span rather than clamped, so a
    caller can see how far out of range a reading is. ``in_range`` says whether
    the raw input was inside the span, inclusive of both ends.
    """
    _check_span(raw_low, raw_high, "raw")
    _check_span(eng_low, eng_high, "engineering")

    fraction = (raw - raw_low) / (raw_high - raw_low)
    value = eng_low + fraction * (eng_high - eng_low)
    return ScaledReading(value=value, in_range=raw_low <= raw <= raw_high)
