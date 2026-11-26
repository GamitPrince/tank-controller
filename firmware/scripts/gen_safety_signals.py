#!/usr/bin/env python3
"""Generate a safety-path signal table from ``interfaces/signals-v1.yaml``.

Story S-022 (P1-05), extended by S-031 (P1-09). ADR-0004 decision 9 made the
versioned YAML signal list the single definition of every signal, so firmware
must not keep a second copy of an id, a channel number, a contact sense or a
debounce figure. This script turns the signals the list marks with a given
``read_by_story`` into one C header, written into the build directory at
build time and never committed.

The header holds an X-macro list rather than finished C objects, so the
firmware decides how to use the contract and adding a channel to the signal
list needs no C change at all. The macro name depends on the story, per
``STORY_TABLES`` below:

    #define TANK_SAFETY_LEVEL_SWITCHES(X) \\
        X(LEVEL_SWITCH_HIGH_HIGH, 3001, 1, TANK_CONTACT_NORMALLY_CLOSED, 200, 50)

Everything the list says about these channels is read, nothing is defaulted: a
missing or unexpected field fails the build instead of producing a table that
quietly disagrees with the contract. In particular a signal that is not
read-only, not boolean, not an optocoupler input or not on the safety path is
refused, because Phase 1 only ever reads these channels, never writes to them
(AGENTS.md section 1).

Usage:
    python gen_safety_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_safety_signals.h --story P1-09
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

#: The X-macro table name, its companion count macro and the header's include
#: guard, per story. Keep P1-05's names unchanged (other code already depends
#: on them); add an entry here for every story this generator is asked to
#: serve. Each story's header has its own guard (and its own file name, set by
#: the build), so one application can include both tables (S-060).
STORY_TABLES = {
    "P1-05": (
        "TANK_SAFETY_LEVEL_SWITCHES",
        "TANK_SAFETY_LEVEL_SWITCH_COUNT",
        "TANK_SAFETY_SIGNALS_H_",
    ),
    "P1-09": (
        "TANK_SAFETY_ALARM_INPUTS",
        "TANK_SAFETY_ALARM_INPUT_COUNT",
        "TANK_ALARM_SIGNALS_H_",
    ),
}

#: Classes that are safety-chain or alarm reads and so belong in
#: firmware/src/safety/ (AGENTS.md section 5), as opposed to equipment-status
#: channels, which are not safety reads.
ALLOWED_CLASSES = {"safety_chain", "alarm"}

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
    "safety_path",
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

#ifndef {guard}
#define {guard}

#define TANK_SIGNAL_LIST_VERSION {version}

#define {count_macro} {count}

#define {table_macro}(X){entries}

#endif /* {guard} */
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
    if entry["safety_path"] is not True:
        raise SignalListError(
            f"signal {signal_id} does not have safety_path: true. This generator "
            "only ever reads channels on the hardwired safety path (AGENTS.md "
            "section 1); an equipment-status channel belongs to a different story."
        )
    if entry["class"] not in ALLOWED_CLASSES:
        raise SignalListError(
            f"signal {signal_id} has class {entry['class']!r}, expected one of "
            f"{sorted(ALLOWED_CLASSES)}"
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
    """Return the C header for the channels ``story`` reads."""
    tables = STORY_TABLES.get(story)
    if tables is None:
        raise SignalListError(
            f"no generated macro name is defined for story {story!r}; "
            "add one to STORY_TABLES"
        )
    table_macro, count_macro, guard = tables

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
        table_macro=table_macro,
        guard=guard,
        count_macro=count_macro,
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
