#!/usr/bin/env python3
"""Generate the equipment-status input table from ``interfaces/signals-v1.yaml``.

Story S-033 (P1-27). ADR-0004 decision 9 made the versioned YAML signal list
the single definition of every signal, so firmware must not keep a second copy
of an id, a channel number, a contact sense or a debounce figure. This script
turns the ``digital`` signals the list marks with ``read_by_story: P1-27`` into
one C header, written into the build directory at build time and never
committed.

This is a sibling of ``gen_safety_signals.py``, not an extension of it, for the
same reason ``gen_temperature_signals.py`` is. The safety generator exists to
serve channels on the hardwired safety path and enforces ``safety_path: true``.
Equipment-status channels (valves, pumps, motor, heaters) are not safety-chain
reads: they report whether equipment is running, they belong in the ordinary
measurement layer, and they must never need the EE's approval or sit under
``firmware/src/safety/`` (AGENTS.md section 5). Teaching the safety generator to
accept them would blur exactly the line that keeps the two apart, so this one
refuses the opposite: a signal with ``safety_path: true`` is an error here.

The header holds an X-macro list, in the same shape the safety tables use so
the same debounced-contact engine can run against it:

    #define TANK_EQUIPMENT_STATUS_INPUTS(X) \\
        X(STATUS_INLET_VALVE, 3021, 3, TANK_CONTACT_NORMALLY_OPEN, 5000, 1000)

Everything the list says about these channels is read, nothing is defaulted: a
missing or unexpected field fails the build instead of producing a table that
quietly disagrees with the contract. The contact sense must be normally open.
The safety and alarm channels are normally closed so a broken wire reads as
alarm; these are normally open so open simply means "not running". The two are
deliberately not harmonised (AGENTS.md section 5), so a normally-closed
equipment-status channel is refused rather than passed through.

Usage:
    python gen_equipment_status_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_equipment_status_signals.h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

#: Signals in this group of the list are the digital inputs.
SIGNAL_GROUP = "digital"

#: Only the signals the list says this story reads are generated here.
STORY = "P1-27"

#: The X-macro table name and its companion count macro.
TABLE_MACRO = "TANK_EQUIPMENT_STATUS_INPUTS"
COUNT_MACRO = "TANK_EQUIPMENT_STATUS_INPUT_COUNT"

#: These are equipment running states, not safety or alarm reads.
REQUIRED_CLASS = "equipment_status"

#: The input device these channels come from (ADR-0002: 16-channel
#: optocoupler digital inputs, status-only, input-only by construction).
REQUIRED_DEVICE = "optocoupler"

#: The only contact sense an equipment-status channel may have (decided
#: 20 Nov 2026): closed means running, open means not running.
REQUIRED_CONTACT_SENSE = "normally_open"
CONTACT_SENSE_ENUM = "TANK_CONTACT_NORMALLY_OPEN"

#: The board has 16 optocoupler channels (ADR-0002).
CHANNEL_RANGE = range(1, 17)

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
 * firmware/scripts/gen_equipment_status_signals.py. Do not edit, and do not
 * commit: the signal list in interfaces/ is the contract, this file is only
 * its C form for story {story}.
 *
 * Each entry is: NAME, signal id, optocoupler channel, contact sense,
 * debounce in ms, scan interval in ms.
 */

#ifndef TANK_EQUIPMENT_STATUS_SIGNALS_H_
#define TANK_EQUIPMENT_STATUS_SIGNALS_H_

#define TANK_SIGNAL_LIST_VERSION {version}

#define {count_macro} {count}

#define {table_macro}(X){entries}

#endif /* TANK_EQUIPMENT_STATUS_SIGNALS_H_ */
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


def _check_phase_1_rules(entry: dict[str, Any]) -> None:
    signal_id = entry["id"]
    source = entry["source"] or {}

    if entry["read_only"] is not True:
        raise SignalListError(
            f"signal {signal_id} is not read_only. Phase 1 reports equipment state "
            "and never commands it, so this is a phase change, not a signal-list edit."
        )
    if entry["safety_path"] is not False:
        raise SignalListError(
            f"signal {signal_id} does not have safety_path: false. A safety-path "
            "channel belongs in firmware/src/safety/ with its own generated table, "
            "not in the measurement layer (AGENTS.md section 5)."
        )
    if entry["class"] != REQUIRED_CLASS:
        raise SignalListError(
            f"signal {signal_id} has class {entry['class']!r}, expected {REQUIRED_CLASS!r}"
        )
    if entry["unit"] != "bool":
        raise SignalListError(f"signal {signal_id} is not a boolean status")
    if source.get("device") != REQUIRED_DEVICE:
        raise SignalListError(
            f"signal {signal_id} comes from {source.get('device')!r}, "
            f"expected {REQUIRED_DEVICE!r}"
        )
    if source.get("channel") not in CHANNEL_RANGE:
        raise SignalListError(
            f"signal {signal_id} has channel {source.get('channel')!r}, outside the "
            f"{CHANNEL_RANGE.start} to {CHANNEL_RANGE.stop - 1} the board is wired for"
        )
    if entry["contact_sense"] != REQUIRED_CONTACT_SENSE:
        raise SignalListError(
            f"signal {signal_id} has contact sense {entry['contact_sense']!r}, "
            f"expected {REQUIRED_CONTACT_SENSE!r}. Equipment-status channels are "
            "normally open on purpose and are not harmonised with the "
            "normally-closed safety and alarm channels."
        )
    for field in ("debounce_ms", "scan_interval_ms"):
        value = entry[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise SignalListError(f"signal {signal_id} needs a positive {field}")


def _check_unique(entries: list[dict[str, Any]]) -> None:
    for field, reader in (
        ("id", lambda entry: entry["id"]),
        ("channel", lambda entry: (entry["source"] or {}).get("channel")),
    ):
        seen: dict[Any, Any] = {}
        for entry in entries:
            value = reader(entry)
            if value in seen:
                raise SignalListError(
                    f"signals {seen[value]} and {entry['id']} share {field} {value!r}; "
                    "one input would be reported under two signal ids"
                )
            seen[value] = entry["id"]


def _entry_to_macro(entry: dict[str, Any]) -> str:
    return "\tX({name}, {id}, {channel}, {sense}, {debounce}, {scan})".format(
        name=str(entry["name"]).upper(),
        id=int(entry["id"]),
        channel=int(entry["source"]["channel"]),
        sense=CONTACT_SENSE_ENUM,
        debounce=int(entry["debounce_ms"]),
        scan=int(entry["scan_interval_ms"]),
    )


def _load_version(raw: dict[str, Any], source: Path) -> int:
    version = raw.get("version")
    if not isinstance(version, int):
        raise SignalListError(f"{source} does not declare an integer version")
    return version


def render_header(signals_path: Path, story: str = STORY) -> str:
    """Return the C header for the equipment-status channels ``story`` reads."""
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

    for entry in entries:
        _check_fields(entry)
        _check_phase_1_rules(entry)

    _check_unique(entries)
    macros = [_entry_to_macro(entry) for entry in entries]

    return HEADER_TEMPLATE.format(
        source_name=signals_path.name,
        version=_load_version(raw, signals_path),
        story=story,
        table_macro=TABLE_MACRO,
        count_macro=COUNT_MACRO,
        count=len(macros),
        entries=" \\\n" + " \\\n".join(macros),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--signals", required=True, type=Path, help="path to interfaces/signals-v1.yaml"
    )
    parser.add_argument("--output", required=True, type=Path, help="header file to write")
    parser.add_argument(
        "--story", default=STORY, help=f"story whose signals to generate (default {STORY})"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        header = render_header(args.signals, args.story)
    except (SignalListError, OSError, yaml.YAMLError) as err:
        print(f"gen_equipment_status_signals: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
