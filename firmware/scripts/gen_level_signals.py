#!/usr/bin/env python3
"""Generate the 4-20 mA level signal table from ``interfaces/signals-v1.yaml``.

Story S-034 (P1-04). ADR-0004 decision 9 made the versioned YAML signal list
the single definition of every signal, so firmware must not keep a second copy
of an id, an AD4111 channel or a valid range. This script turns the
``analogue`` signals the list marks with ``read_by_story: P1-04`` (radar level
and pressure level) into one C header, written into the build directory at
build time and never committed.

It is a sibling of ``gen_temperature_signals.py`` and ``gen_safety_signals.py``,
not an extension of them: the rules differ (an AD4111 channel and a mA unit,
no chip select, no contact sense), and teaching one generator all of them would
mean relaxing the checks that keep a non-safety channel out of
``firmware/src/safety/``.

The header holds an X-macro list:

    #define TANK_LEVEL_LOOPS(X) \\
        X(LEVEL_RADAR_LOOP_CURRENT, 1001, 1, 1000, 4.0f, 20.0f)

Every field is read from the list, nothing is defaulted. ``scale`` is required
but not emitted: the record layer applies it.

Usage:
    python gen_level_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_level_signals.h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

SIGNAL_GROUP = "analogue"
STORY = "P1-04"
TABLE_MACRO = "TANK_LEVEL_LOOPS"
COUNT_MACRO = "TANK_LEVEL_LOOP_COUNT"

REQUIRED_CLASS = "measurement"
REQUIRED_DEVICE = "AD4111"
REQUIRED_UNIT = "mA"

#: ADR-0002: two of the four AD4111 current inputs are used in Phase 1.
CHANNEL_RANGE = range(1, 3)

REQUIRED_FIELDS = (
    "id",
    "name",
    "class",
    "unit",
    "scale",
    "valid_range",
    "update_rate_ms",
    "read_only",
    "source",
)
REQUIRED_SOURCE_FIELDS = ("device", "channel")

HEADER_TEMPLATE = """\
/*
 * Generated from {source_name} (signal list version {version}) by
 * firmware/scripts/gen_level_signals.py. Do not edit, and do not commit:
 * the signal list in interfaces/ is the contract, this file is only its C
 * form for story {story}.
 *
 * Each entry is: NAME, signal id, AD4111 channel, update rate in ms, valid
 * range low and high in mA.
 */

#ifndef TANK_LEVEL_SIGNALS_H_
#define TANK_LEVEL_SIGNALS_H_

#define TANK_SIGNAL_LIST_VERSION {version}

#define {count_macro} {count}

#define {table_macro}(X){entries}

#endif /* TANK_LEVEL_SIGNALS_H_ */
"""


class SignalListError(RuntimeError):
    """Raised when the signal list cannot be turned into a valid table."""


def _check_fields(entry: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in entry]
    if missing:
        raise SignalListError(
            f"signal {entry.get('id', '?')} is missing {', '.join(missing)}; "
            "the generator does not default a signal-list field"
        )
    source = entry["source"] or {}
    missing_source = [field for field in REQUIRED_SOURCE_FIELDS if field not in source]
    if missing_source:
        raise SignalListError(
            f"signal {entry['id']} is missing source.{', source.'.join(missing_source)}"
        )


def _check_phase_1_rules(entry: dict[str, Any]) -> None:
    signal_id = entry["id"]
    source = entry["source"]

    if entry["read_only"] is not True:
        raise SignalListError(
            f"signal {signal_id} is not read_only. Phase 1 is read-only monitoring."
        )
    if entry.get("safety_path") is True:
        raise SignalListError(
            f"signal {signal_id} has safety_path: true; it belongs in firmware/src/safety/."
        )
    if entry["class"] != REQUIRED_CLASS:
        raise SignalListError(
            f"signal {signal_id} has class {entry['class']!r}, expected {REQUIRED_CLASS!r}"
        )
    if entry["unit"] != REQUIRED_UNIT:
        raise SignalListError(
            f"signal {signal_id} has unit {entry['unit']!r}, expected {REQUIRED_UNIT!r}"
        )
    if source["device"] != REQUIRED_DEVICE:
        raise SignalListError(
            f"signal {signal_id} has source.device {source['device']!r}, "
            f"expected {REQUIRED_DEVICE!r}"
        )
    if source["channel"] not in CHANNEL_RANGE:
        raise SignalListError(
            f"signal {signal_id} has AD4111 channel {source['channel']!r}, outside "
            f"{CHANNEL_RANGE.start} to {CHANNEL_RANGE.stop - 1}"
        )
    if not isinstance(entry["update_rate_ms"], int) or entry["update_rate_ms"] <= 0:
        raise SignalListError(f"signal {signal_id} has no positive update_rate_ms")

    valid_range = entry["valid_range"]
    if not isinstance(valid_range, list) or len(valid_range) != 2:
        raise SignalListError(f"signal {signal_id} needs a valid_range of two values")
    low, high = valid_range
    if not all(isinstance(v, (int, float)) for v in (low, high)):
        raise SignalListError(f"signal {signal_id} has a non-numeric valid_range")
    if low >= high:
        raise SignalListError(
            f"signal {signal_id} has valid_range [{low}, {high}], which is empty or inverted"
        )


def _check_unique(entries: list[dict[str, Any]]) -> None:
    for field, reader in (
        ("id", lambda entry: entry["id"]),
        ("AD4111 channel", lambda entry: entry["source"]["channel"]),
    ):
        seen: dict[Any, Any] = {}
        for entry in entries:
            value = reader(entry)
            if value in seen:
                raise SignalListError(
                    f"signals {seen[value]} and {entry['id']} share {field} {value!r}; "
                    "one channel would be reported under another's signal id"
                )
            seen[value] = entry["id"]


def _entry_to_macro(entry: dict[str, Any]) -> str:
    low, high = entry["valid_range"]
    return "\tX({name}, {id}, {channel}, {rate}, {low:.1f}f, {high:.1f}f)".format(
        name=str(entry["name"]).upper(),
        id=int(entry["id"]),
        channel=int(entry["source"]["channel"]),
        rate=int(entry["update_rate_ms"]),
        low=float(low),
        high=float(high),
    )


def render_header(signals_path: Path, story: str = STORY) -> str:
    """Return the C header for the 4-20 mA signals ``story`` reads."""
    raw = yaml.safe_load(signals_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SignalListError(f"{signals_path} does not contain a YAML mapping")

    version = raw.get("version")
    if not isinstance(version, int):
        raise SignalListError(f"{signals_path} does not declare an integer version")

    entries = [
        entry
        for entry in (raw.get(SIGNAL_GROUP) or ())
        if entry.get("read_by_story") == story
    ]
    if not entries:
        raise SignalListError(
            f"{signals_path} has no {SIGNAL_GROUP} signal with read_by_story: {story}"
        )

    for entry in entries:
        _check_fields(entry)
        _check_phase_1_rules(entry)
    _check_unique(entries)

    macros = [_entry_to_macro(entry) for entry in entries]
    return HEADER_TEMPLATE.format(
        source_name=signals_path.name,
        version=version,
        story=story,
        table_macro=TABLE_MACRO,
        count_macro=COUNT_MACRO,
        count=len(macros),
        entries=" \\\n" + " \\\n".join(macros),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--story", default=STORY)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        header = render_header(args.signals, args.story)
    except (SignalListError, OSError, yaml.YAMLError) as err:
        print(f"gen_level_signals: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
