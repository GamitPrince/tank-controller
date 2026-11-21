"""The Phase 1 signal list, loaded from ``interfaces/signals-v1.yaml``.

ADR-0004 decision 9 replaced the register map with a versioned YAML signal
list identified by numeric ids. This module is the only place the simulator
learns what signals exist, what they are called, what their scale and valid
range are, and how the digital channels are wired. Nothing here is hardcoded.

The loader also enforces the Phase 1 invariant that the list itself states: the
controller is send-only and the hardwired safety chain is only ever read, so a
signal with ``read_only: false`` is a phase change, not a signal-list edit. A
writable signal makes the load fail rather than letting the simulator pretend
it could drive anything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from .interfaces import signal_list_path

# The top-level keys of the signal list that hold signals, in record order. A
# key the loader does not know is an error: silently skipping a new group would
# mean quietly not simulating part of the plant.
SIGNAL_GROUPS = ("analogue", "temperature", "digital", "health")

# Keys that describe the list rather than a signal.
_METADATA_KEYS = ("version", "status", "list_date", "story", "phase")

_REQUIRED_SIGNAL_KEYS = ("id", "name", "class", "unit", "scale", "read_only")


class SignalListError(ValueError):
    """Raised when the signal list is missing, malformed or not Phase 1."""


@dataclass(frozen=True)
class Signal:
    """One signal the device sends, exactly as the signal list describes it."""

    id: int
    name: str
    group: str
    signal_class: str
    unit: str
    scale: float
    update_rate_ms: int
    read_only: bool
    description: str = ""
    valid_range: tuple[float, float] | None = None
    accuracy_degc: float | None = None
    contact_sense: str | None = None
    value_true_means: str | None = None
    debounce_ms: int | None = None
    scan_interval_ms: int | None = None
    safety_path: bool = False
    source: Mapping[str, Any] = MappingProxyType({})
    read_by_story: str | None = None

    @property
    def is_boolean(self) -> bool:
        """True when the transmitted value is a bool rather than a scaled int."""
        return self.unit == "bool"

    def to_raw(self, engineering_value: float) -> int:
        """Convert an engineering value into the integer the record carries.

        The record sends scaled integers, never floats (``interfaces/records.cddl``),
        so the transmitted value is the engineering value divided by ``scale``.
        """
        if self.is_boolean:
            raise SignalListError(f"signal {self.id} is boolean and has no scaled value")
        return round(engineering_value / self.scale)

    def to_engineering(self, raw: int) -> float:
        """Inverse of :meth:`to_raw`, for a consumer reading a record back."""
        return raw * self.scale


@dataclass(frozen=True)
class SignalList:
    """An immutable, indexed view of one version of the signal list."""

    version: int
    status: str
    signals: tuple[Signal, ...]

    def __post_init__(self) -> None:
        by_id: dict[int, Signal] = {}
        by_name: dict[str, Signal] = {}
        for signal in self.signals:
            if signal.id in by_id:
                raise SignalListError(f"duplicate signal id {signal.id}")
            if signal.name in by_name:
                raise SignalListError(f"duplicate signal name {signal.name!r}")
            by_id[signal.id] = signal
            by_name[signal.name] = signal
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_by_name", MappingProxyType(by_name))

    def __len__(self) -> int:
        return len(self.signals)

    def __iter__(self):
        return iter(self.signals)

    def by_id(self, signal_id: int) -> Signal:
        """Look a signal up by the id a record carries."""
        try:
            return self._by_id[signal_id]  # type: ignore[attr-defined]
        except KeyError:
            raise SignalListError(f"no signal with id {signal_id}") from None

    def by_name(self, name: str) -> Signal:
        """Look a signal up by the snake_case name used in code and the API."""
        try:
            return self._by_name[name]  # type: ignore[attr-defined]
        except KeyError:
            raise SignalListError(f"no signal named {name!r}") from None

    def in_group(self, group: str) -> tuple[Signal, ...]:
        """Every signal in one of :data:`SIGNAL_GROUPS`."""
        return tuple(s for s in self.signals if s.group == group)

    def safety_path_signals(self) -> tuple[Signal, ...]:
        """Signals read from the hardwired safety chain or an alarm contact.

        They are status inputs only. The simulator produces them so firmware and
        the dashboard can be exercised; it never produces an output to them.
        """
        return tuple(s for s in self.signals if s.safety_path)


def _valid_range_from(entry: Mapping[str, Any]) -> tuple[float, float] | None:
    declared = entry.get("valid_range")
    if declared is None:
        return None
    low, high = (float(v) for v in declared)
    if high <= low:
        raise SignalListError(f"signal {entry['id']} has an inverted valid_range")
    return (low, high)


def _signal_from_mapping(group: str, entry: Mapping[str, Any]) -> Signal:
    missing = [key for key in _REQUIRED_SIGNAL_KEYS if key not in entry]
    if missing:
        raise SignalListError(f"signal in group {group!r} is missing {', '.join(missing)}")

    if entry["read_only"] is not True:
        raise SignalListError(
            f"signal {entry['id']} ({entry['name']}) is not read_only. Phase 1 is "
            "read-only monitoring and the safety chain is only ever read, so a "
            "writable signal is a phase change, not a signal-list edit."
        )

    return Signal(
        id=int(entry["id"]),
        name=str(entry["name"]),
        group=group,
        signal_class=str(entry["class"]),
        unit=str(entry["unit"]),
        scale=float(entry["scale"]),
        update_rate_ms=int(entry.get("update_rate_ms", 0)),
        read_only=True,
        description=str(entry.get("description", "")).strip(),
        valid_range=_valid_range_from(entry),
        accuracy_degc=entry.get("accuracy_degc"),
        contact_sense=entry.get("contact_sense"),
        value_true_means=entry.get("value_true_means"),
        debounce_ms=entry.get("debounce_ms"),
        scan_interval_ms=entry.get("scan_interval_ms"),
        safety_path=bool(entry.get("safety_path", False)),
        source=MappingProxyType(dict(entry.get("source") or {})),
        read_by_story=entry.get("read_by_story"),
    )


def load_signal_list(path: Path | None = None, expected_version: int = 1) -> SignalList:
    """Load and check the signal list.

    ``expected_version`` is checked against the ``version:`` field inside the
    file, not just the filename: the version rule in ``interfaces/README.md``
    puts it in both so a parser can refuse a mismatch.
    """
    source_path = path or signal_list_path(version=expected_version)
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SignalListError(f"signal list not found at {source_path}") from None

    if not isinstance(raw, dict):
        raise SignalListError(f"{source_path} does not contain a YAML mapping")

    version = raw.get("version")
    if version != expected_version:
        raise SignalListError(
            f"{source_path} declares version {version!r}, expected {expected_version}"
        )

    unknown = set(raw) - set(SIGNAL_GROUPS) - set(_METADATA_KEYS)
    if unknown:
        raise SignalListError(
            f"{source_path} has group(s) this loader does not know: {sorted(unknown)}. "
            "Teach the simulator about them rather than skipping them."
        )

    signals: list[Signal] = []
    for group in SIGNAL_GROUPS:
        for entry in raw.get(group) or ():
            signals.append(_signal_from_mapping(group, entry))

    if not signals:
        raise SignalListError(f"{source_path} defines no signals")

    return SignalList(
        version=int(version),
        status=str(raw.get("status", "unknown")),
        signals=tuple(signals),
    )
