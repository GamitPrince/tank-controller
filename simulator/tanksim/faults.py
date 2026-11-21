"""Fault injection.

The story's acceptance criteria name three faults: a sensor fault, an
out-of-range value and a link drop. A fault is described as a window of scan
numbers rather than wall-clock seconds, so a scenario replays identically on a
fast machine and a slow one.

``[Confirm]`` The spec left the fault-injection interface open (config file, CLI
flags or an API). All three are provided from one definition: :class:`FaultPlan`
is the API, :func:`parse_signal_fault` and :func:`parse_link_drop` back the CLI
flags, and :func:`plan_from_scenario` reads the same fields out of a JSON file
for a scenario worth keeping. Nothing is defined twice.

A fault never produces a *value* the schema forbids: a sensor fault sends no
value at all, because a failed sensor is flagged and excluded, never silently
replaced (AGENTS.md section 7).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .signals import SignalList

#: Sensor or bus failure: the reading is flagged ``fault`` and carries no value.
SENSOR_FAULT = "sensor_fault"
#: The sensor answers, but with a value outside the signal's ``valid_range``.
OUT_OF_RANGE = "out_of_range"
#: The value was not refreshed this scan: the last one is sent, flagged stale.
STALE = "stale"

FAULT_KINDS = (SENSOR_FAULT, OUT_OF_RANGE, STALE)

#: How far outside the valid range an injected out-of-range value sits, as a
#: fraction of the range width. Small enough to be a credible drifting sensor,
#: large enough that no rounding could bring it back inside.
OUT_OF_RANGE_OVERSHOOT = 0.1


class FaultError(ValueError):
    """Raised when a fault specification is not usable."""


@dataclass(frozen=True)
class ScanWindow:
    """An inclusive window of scan numbers, open-ended when ``last`` is None."""

    first: int = 0
    last: int | None = None

    def __post_init__(self) -> None:
        if self.first < 0:
            raise FaultError("a scan window cannot start before scan 0")
        if self.last is not None and self.last < self.first:
            raise FaultError(f"scan window {self.first}-{self.last} ends before it starts")

    def contains(self, scan: int) -> bool:
        """Whether ``scan`` falls inside the window."""
        return scan >= self.first and (self.last is None or scan <= self.last)

    def __str__(self) -> str:
        return f"{self.first}-{'end' if self.last is None else self.last}"


@dataclass(frozen=True)
class SignalFault:
    """One injected fault on one signal."""

    signal_id: int
    kind: str
    window: ScanWindow = field(default_factory=ScanWindow)

    def __post_init__(self) -> None:
        if self.kind not in FAULT_KINDS:
            raise FaultError(f"unknown fault kind {self.kind!r}; choose one of {FAULT_KINDS}")


@dataclass(frozen=True)
class LinkDrop:
    """A window in which the link to the cloud is down."""

    window: ScanWindow

    def __post_init__(self) -> None:
        if self.window.first == 0 and self.window.last is None:
            raise FaultError(
                "a link drop covering every scan would never deliver a record; "
                "give it a start or an end"
            )


@dataclass(frozen=True)
class FaultPlan:
    """Every fault to inject during a run."""

    signal_faults: tuple[SignalFault, ...] = ()
    link_drops: tuple[LinkDrop, ...] = ()

    def kind_for(self, signal_id: int, scan: int) -> str | None:
        """The fault active on ``signal_id`` at ``scan``, if any.

        When two faults overlap, the first one given wins, so a scenario file
        reads top to bottom.
        """
        for fault in self.signal_faults:
            if fault.signal_id == signal_id and fault.window.contains(scan):
                return fault.kind
        return None

    def link_down(self, scan: int) -> bool:
        """Whether the link is down at ``scan``."""
        return any(drop.window.contains(scan) for drop in self.link_drops)

    def validate_against(self, signal_list: SignalList) -> None:
        """Check every fault against the signal list.

        A fault on an unknown id, or an out-of-range fault on a signal that has
        no range to leave, is a mistake in the scenario and is reported before
        the run starts rather than halfway through it.
        """
        for fault in self.signal_faults:
            signal = signal_list.by_id(fault.signal_id)
            if fault.kind == OUT_OF_RANGE and signal.valid_range is None:
                raise FaultError(
                    f"signal {signal.id} ({signal.name}) has no valid_range, so an "
                    f"{OUT_OF_RANGE} fault has no meaning for it"
                )


def _parse_window(text: str) -> ScanWindow:
    """Parse ``first``, ``first-``, ``first-last`` or an empty string."""
    text = text.strip()
    if not text:
        return ScanWindow()
    if "-" not in text:
        scan = _parse_int(text, "scan number")
        return ScanWindow(first=scan, last=scan)
    first_text, last_text = text.split("-", 1)
    first = _parse_int(first_text, "window start") if first_text.strip() else 0
    last = _parse_int(last_text, "window end") if last_text.strip() else None
    return ScanWindow(first=first, last=last)


def _parse_int(text: str, what: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise FaultError(f"{what} {text.strip()!r} is not a whole number") from None


def parse_signal_fault(spec: str) -> SignalFault:
    """Parse a CLI fault flag: ``<signal-id>:<kind>[@<window>]``.

    Examples: ``2001:sensor_fault``, ``1001:out_of_range@5-9``, ``3001:stale@7``.
    """
    body, _, window_text = spec.partition("@")
    signal_text, separator, kind = body.partition(":")
    if not separator or not kind.strip():
        raise FaultError(
            f"fault {spec!r} should look like <signal-id>:<kind>[@<first>-<last>], "
            f"kind being one of {FAULT_KINDS}"
        )
    return SignalFault(
        signal_id=_parse_int(signal_text, "signal id"),
        kind=kind.strip(),
        window=_parse_window(window_text),
    )


def parse_link_drop(spec: str) -> LinkDrop:
    """Parse a CLI link-drop flag: ``<first>-<last>``, ``<first>-`` or ``<scan>``."""
    return LinkDrop(window=_parse_window(spec))


def _window_from_mapping(entry: dict[str, Any]) -> ScanWindow:
    return ScanWindow(
        first=int(entry.get("first_scan", 0)),
        last=None if entry.get("last_scan") is None else int(entry["last_scan"]),
    )


def plan_from_scenario(scenario: dict[str, Any]) -> FaultPlan:
    """Build a plan from a decoded scenario mapping.

    The shape is the API's, spelled out in JSON::

        {"signal_faults": [{"signal_id": 2001, "kind": "sensor_fault",
                            "first_scan": 3, "last_scan": 6}],
         "link_drops":    [{"first_scan": 10, "last_scan": 14}]}
    """
    unknown = set(scenario) - {"signal_faults", "link_drops"}
    if unknown:
        raise FaultError(f"scenario has unknown key(s) {sorted(unknown)}")
    faults = tuple(
        SignalFault(
            signal_id=int(entry["signal_id"]),
            kind=str(entry["kind"]),
            window=_window_from_mapping(entry),
        )
        for entry in scenario.get("signal_faults", ())
    )
    drops = tuple(
        LinkDrop(window=_window_from_mapping(entry)) for entry in scenario.get("link_drops", ())
    )
    return FaultPlan(signal_faults=faults, link_drops=drops)


def load_scenario(path: Path) -> FaultPlan:
    """Read a scenario file and build the plan it describes."""
    try:
        scenario = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FaultError(f"scenario file {path} not found") from None
    except json.JSONDecodeError as error:
        raise FaultError(f"scenario file {path} is not valid JSON: {error}") from None
    if not isinstance(scenario, dict):
        raise FaultError(f"scenario file {path} must hold a JSON object")
    return plan_from_scenario(scenario)


def out_of_range_value(low: float, high: float) -> float:
    """A value just outside ``low..high``, for an injected out-of-range fault."""
    return high + (high - low) * OUT_OF_RANGE_OVERSHOOT
