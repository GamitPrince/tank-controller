#!/usr/bin/env python3
"""Generate a health-signal table from ``interfaces/signals-v1.yaml``.

Story S-038 (P1-15). ADR-0004 decision 9 made the versioned YAML signal list
the single definition of every signal, so firmware must not keep a second
copy of an id. This script turns the ``health`` signals the list marks with
a given ``read_by_story`` into one C header, written into the build
directory at build time and never committed.

It is a sibling of ``gen_level_signals.py`` and ``gen_equipment_status_signals.py``,
not an extension of them: health signals have no channel, contact sense or
valid range, so the table is simpler: NAME, signal id, scale, update rate.

Usage:
    python gen_health_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_health_signals.h --story P1-15
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

SIGNAL_GROUP = "health"
STORY = "P1-15"
TABLE_MACRO = "TANK_HEALTH_SIGNALS"
COUNT_MACRO = "TANK_HEALTH_SIGNAL_COUNT"

REQUIRED_CLASS = "health"
REQUIRED_DEVICE = "controller"

REQUIRED_FIELDS = ("id", "name", "class", "unit", "scale", "update_rate_ms", "read_only", "source")
REQUIRED_SOURCE_FIELDS = ("device",)

HEADER_TEMPLATE = """\
/*
 * Generated from {source_name} (signal list version {version}) by
 * firmware/scripts/gen_health_signals.py. Do not edit, and do not commit:
 * the signal list in interfaces/ is the contract, this file is only its C
 * form for story {story}.
 *
 * Each entry is: NAME, signal id, scale (x1000, so a float scale survives as
 * an integer), update rate in ms.
 */

#ifndef TANK_HEALTH_SIGNALS_H_
#define TANK_HEALTH_SIGNALS_H_

#define TANK_SIGNAL_LIST_VERSION {version}

#define {count_macro} {count}

#define {table_macro}(X){entries}

#endif /* TANK_HEALTH_SIGNALS_H_ */
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
        raise SignalListError(f"signal {entry['id']} is missing source.{', source.'.join(missing_source)}")


def _check_phase_1_rules(entry: dict[str, Any]) -> None:
    signal_id = entry["id"]
    source = entry["source"]

    if entry["read_only"] is not True:
        raise SignalListError(f"signal {signal_id} is not read_only. Phase 1 is read-only monitoring.")
    if entry["class"] != REQUIRED_CLASS:
        raise SignalListError(f"signal {signal_id} has class {entry['class']!r}, expected {REQUIRED_CLASS!r}")
    if source["device"] != REQUIRED_DEVICE:
        raise SignalListError(
            f"signal {signal_id} has source.device {source['device']!r}, expected {REQUIRED_DEVICE!r}"
        )
    if not isinstance(entry["update_rate_ms"], int) or entry["update_rate_ms"] <= 0:
        raise SignalListError(f"signal {signal_id} has no positive update_rate_ms")
    if not isinstance(entry["scale"], (int, float)) or entry["scale"] <= 0:
        raise SignalListError(f"signal {signal_id} has no positive numeric scale")


def _check_unique(entries: list[dict[str, Any]]) -> None:
    seen: dict[Any, Any] = {}
    for entry in entries:
        value = entry["id"]
        if value in seen:
            raise SignalListError(f"signals {seen[value]} and {value} share id {value!r}")
        seen[value] = entry["id"]


def _entry_to_macro(entry: dict[str, Any]) -> str:
    scale_x1000 = round(float(entry["scale"]) * 1000)
    return "\tX({name}, {id}, {scale_x1000}, {rate})".format(
        name=str(entry["name"]).upper(),
        id=int(entry["id"]),
        scale_x1000=scale_x1000,
        rate=int(entry["update_rate_ms"]),
    )


def render_header(signals_path: Path, story: str = STORY) -> str:
    """Return the C header for the health signals ``story`` reads."""
    raw = yaml.safe_load(signals_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SignalListError(f"{signals_path} does not contain a YAML mapping")

    version = raw.get("version")
    if not isinstance(version, int):
        raise SignalListError(f"{signals_path} does not declare an integer version")

    entries = [entry for entry in (raw.get(SIGNAL_GROUP) or ()) if entry.get("read_by_story") == story]
    if not entries:
        raise SignalListError(f"{signals_path} has no {SIGNAL_GROUP} signal with read_by_story: {story}")

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
        print(f"gen_health_signals: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
