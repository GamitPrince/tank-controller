#!/usr/bin/env python3
"""Generate the safety-chain switch table from ``interfaces/signals-v1.yaml``.

Story S-022 (P1-05). ADR-0004 decision 9 made the versioned YAML signal list
the single definition of every signal, so firmware must not keep a second copy
of an id, a channel number, a contact sense or a debounce figure. This script
turns the signals the list marks ``read_by_story: P1-05`` into one C header,
written into the build directory at build time and never committed.

The header holds an X-macro list rather than finished C objects, so the
firmware decides how to use the contract and adding a switch to the signal list
needs no C change at all:

    #define TANK_SAFETY_LEVEL_SWITCHES(X) \\
        X(LEVEL_SWITCH_HIGH_HIGH, 3001, 1, TANK_CONTACT_NORMALLY_CLOSED, 200, 50)

Everything the list says about these channels is read, nothing is defaulted: a
missing or unexpected field fails the build instead of producing a table that
quietly disagrees with the contract. In particular a signal that is not
read-only, not boolean, not an optocoupler input or not in the safety-chain
class is refused, because Phase 1 reads the hardwired safety chain and never
writes to it (AGENTS.md section 1).

Usage:
    python gen_safety_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_safety_signals.h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

#: Signals in this group of the list are the digital inputs.
SIGNAL_GROUP = "digital"

#: Only the signals the list says this story reads are generated here. The
#: alarm channels (10 to 15) are story P1-09 and the equipment-status channels
#: (3 to 9) are P1-27, each with its own table.
STORY = "P1-05"

#: The class the signal list gives the hardwired safety chain.
REQUIRED_CLASS = "safety_chain"

#: The input device these channels come from (ADR-0002: 16-channel
#: optocoupler digital inputs, status-only, input-only by construction).
REQUIRED_DEVICE = "optocoupler"

#: Contact senses the firmware understands, mapped onto the C enumerators.
CONTACT_SENSES = {
    "normally_closed": "TANK_CONTACT_NORMALLY_CLOSED",
    "normally_open": "TANK_CONTACT_NORMALLY_OPEN",
}

#: Fields each generated signal must carry. None is optional.
REQUIRED_FIELDS = (
    "id",
    "name",
    "class",
    "unit",
    "read_only",
    "source",
    "contact_sense",
    "debounce_ms",
    "scan_interval_ms",
)

HEADER_TEMPLATE = """\
/*
 * Generated from {source_name} (signal list version {version}) by
 * firmware/scripts/gen_safety_signals.py. Do not edit, and do not commit:
 * the signal list in interfaces/ is the contract, this file is only its C
 * form for story {story}.
 *
 * Each entry is: NAME, signal id, optocoupler channel, contact sense,
 * debounce in ms, scan interval in ms.
 */

#ifndef TANK_SAFETY_SIGNALS_H_
#define TANK_SAFETY_SIGNALS_H_

#define TANK_SIGNAL_LIST_VERSION {version}

#define TANK_SAFETY_LEVEL_SWITCH_COUNT {count}

#define TANK_SAFETY_LEVEL_SWITCHES(X){entries}

#endif /* TANK_SAFETY_SIGNALS_H_ */
"""


class SignalListError(RuntimeError):
    """Raised when the signal list cannot be turned into a valid table."""


def _check_fields(entry: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in entry]
    if missing:
        raise SignalListError(
            f"signal {entry.get('id', '?')} is missing {', '.join(missing)}; "
            "the generator does not default a safety-chain field"
        )


def _check_phase_1_rules(entry: dict[str, Any]) -> None:
    signal_id = entry["id"]
    if entry["read_only"] is not True:
        raise SignalListError(
            f"signal {signal_id} is not read_only. Phase 1 reads the hardwired "
            "safety chain and never writes to it, so this is a phase change, "
            "not a signal-list edit."
        )
    if entry["class"] != REQUIRED_CLASS:
        raise SignalListError(
            f"signal {signal_id} has class {entry['class']!r}, expected {REQUIRED_CLASS!r}"
        )
    if entry["unit"] != "bool":
        raise SignalListError(f"signal {signal_id} is not a boolean switch state")
    device = (entry["source"] or {}).get("device")
    if device != REQUIRED_DEVICE:
        raise SignalListError(
            f"signal {signal_id} comes from {device!r}, expected {REQUIRED_DEVICE!r}"
        )


def _entry_to_macro(entry: dict[str, Any]) -> str:
    _check_fields(entry)
    _check_phase_1_rules(entry)

    sense = CONTACT_SENSES.get(entry["contact_sense"])
    if sense is None:
        raise SignalListError(
            f"signal {entry['id']} has contact sense {entry['contact_sense']!r}, "
            f"which the firmware does not understand (known: {sorted(CONTACT_SENSES)})"
        )

    channel = (entry["source"] or {}).get("channel")
    if channel is None:
        raise SignalListError(f"signal {entry['id']} has no source channel")

    return "\tX({name}, {id}, {channel}, {sense}, {debounce}, {scan})".format(
        name=str(entry["name"]).upper(),
        id=int(entry["id"]),
        channel=int(channel),
        sense=sense,
        debounce=int(entry["debounce_ms"]),
        scan=int(entry["scan_interval_ms"]),
    )


def _load_version(raw: dict[str, Any], source: Path) -> int:
    version = raw.get("version")
    if not isinstance(version, int):
        raise SignalListError(f"{source} does not declare an integer version")
    return version


def render_header(signals_path: Path, story: str = STORY) -> str:
    """Return the C header for the switches ``story`` reads."""
    raw = yaml.safe_load(signals_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SignalListError(f"{signals_path} does not contain a YAML mapping")

    entries = [
        entry
        for entry in (raw.get(SIGNAL_GROUP) or ())
        if entry.get("read_by_story") == story
    ]
    if not entries:
        raise SignalListError(
            f"{signals_path} has no {SIGNAL_GROUP} signal with read_by_story: {story}"
        )

    macros = [_entry_to_macro(entry) for entry in entries]

    return HEADER_TEMPLATE.format(
        source_name=signals_path.name,
        version=_load_version(raw, signals_path),
        story=story,
        count=len(macros),
        entries=" \\\n" + " \\\n".join(macros),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signals", required=True, type=Path, help="path to interfaces/signals-v1.yaml"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="header file to write"
    )
    parser.add_argument(
        "--story", default=STORY, help=f"story whose signals to generate (default {STORY})"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        header = render_header(args.signals, args.story)
    except (SignalListError, OSError, yaml.YAMLError) as err:
        print(f"gen_safety_signals: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
