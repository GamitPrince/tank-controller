#!/usr/bin/env python3
"""Generate the PT100 temperature signal table from ``interfaces/signals-v1.yaml``.

Story S-032 (P1-06). ADR-0004 decision 9 made the versioned YAML signal list
the single definition of every signal, so firmware must not keep a second copy
of an id, a chip select, a mounting position or a valid range. This script
turns the ``temperature`` signals the list marks with ``read_by_story: P1-06``
into one C header, written into the build directory at build time and never
committed.

This is a sibling of ``gen_safety_signals.py``, not an extension of it. That
script serves the safety-path digital channels and enforces rules that only
make sense there: ``safety_path: true``, a boolean unit, an optocoupler source,
a contact sense and a debounce figure. The PT100 signals are ``measurement``
class in the ``temperature`` group with none of those fields, so teaching the
safety generator to accept them would mean relaxing exactly the checks that
keep a non-safety channel out of ``firmware/src/safety/``. The X-macro and
generated-header pattern is shared; the rules are not.

The header holds an X-macro list rather than finished C objects, so the
firmware decides how to use the contract and adding a sensor to the signal list
needs no C change at all:

    #define TANK_TEMPERATURE_SENSORS(X) \\
        X(TEMP_PRODUCT_UPPER_A, 2001, 1, TANK_PRODUCT_LEVEL_UPPER, 0, 1000, 0.0f, 200.0f)

Every field the generated table carries is read from the list, nothing is
defaulted: a missing or unexpected field fails the build instead of producing a
table that quietly disagrees with the contract. Fields that belong to another
layer, such as ``scale`` and ``accuracy_degc``, are required to be present but
are not emitted, so dropping one from the list still fails the build even
though the measurement layer does not use it.

Two sensors sharing a chip select is refused: the chip select is the only thing
that distinguishes one PT100 from another on this shared SPI bus (ADR-0002), so
a duplicate would silently report one sensor's reading under another's signal
id. That is the misaddressing fault the P1-06 test plan calls out, caught at
build time rather than on the bench.

Usage:
    python gen_temperature_signals.py --signals interfaces/signals-v1.yaml \\
        --output build/generated/tank_temperature_signals.h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

#: Signals in this group of the list are the PT100 temperature reads.
SIGNAL_GROUP = "temperature"

#: Only the signals the list says this story reads are generated here.
STORY = "P1-06"

#: The X-macro table name and its companion count macro.
TABLE_MACRO = "TANK_TEMPERATURE_SENSORS"
COUNT_MACRO = "TANK_TEMPERATURE_SENSOR_COUNT"

#: These are product temperature measurements, not safety or alarm reads. A
#: signal on the safety path belongs in firmware/src/safety/ and must not be
#: served from here (AGENTS.md section 5).
REQUIRED_CLASS = "measurement"

#: The converter and sensor these channels come from (ADR-0002: six 3-wire
#: PT100s on one MAX31865, a separate chip select per channel).
REQUIRED_DEVICE = "MAX31865"
REQUIRED_SENSOR = "PT100"
REQUIRED_WIRING = "3-wire"
REQUIRED_UNIT = "degC"

#: The MAX31865 carries one chip select per channel; ADR-0002 fits six.
CHIP_SELECT_RANGE = range(1, 7)

#: Mounting heights the firmware understands, mapped onto the C enumerators.
#: This is the sensor's height on the tank, not the tank's fill level.
PRODUCT_LEVELS = {
    "upper": "TANK_PRODUCT_LEVEL_UPPER",
    "middle": "TANK_PRODUCT_LEVEL_MIDDLE",
    "bottom": "TANK_PRODUCT_LEVEL_BOTTOM",
}

#: The two positions of a pair, 180 degrees apart across the tank diameter.
ORIENTATIONS_DEG = (0, 180)

#: Fields each generated signal must carry. None is optional. `scale` and
#: `accuracy_degc` are checked but not emitted: the record layer applies the
#: scale and the accuracy target is verified at bench by P1-25.
REQUIRED_FIELDS = (
    "id",
    "name",
    "class",
    "unit",
    "scale",
    "valid_range",
    "accuracy_degc",
    "update_rate_ms",
    "read_only",
    "source",
)

#: Fields of `source` each generated signal must carry.
REQUIRED_SOURCE_FIELDS = (
    "device",
    "chip_select",
    "sensor",
    "wiring",
    "level",
    "orientation_deg",
)

HEADER_TEMPLATE = """\
/*
 * Generated from {source_name} (signal list version {version}) by
 * firmware/scripts/gen_temperature_signals.py. Do not edit, and do not commit:
 * the signal list in interfaces/ is the contract, this file is only its C
 * form for story {story}.
 *
 * Each entry is: NAME, signal id, chip select, mounting level, orientation in
 * degrees, update rate in ms, valid range low and high in degrees Celsius.
 */

#ifndef TANK_TEMPERATURE_SIGNALS_H_
#define TANK_TEMPERATURE_SIGNALS_H_

#define TANK_SIGNAL_LIST_VERSION {version}

#define {count_macro} {count}

#define {table_macro}(X){entries}

#endif /* TANK_TEMPERATURE_SIGNALS_H_ */
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
    source = entry["source"] or {}

    if entry["read_only"] is not True:
        raise SignalListError(
            f"signal {signal_id} is not read_only. Phase 1 is read-only monitoring, "
            "so this is a phase change, not a signal-list edit."
        )
    if entry.get("safety_path") is True:
        raise SignalListError(
            f"signal {signal_id} has safety_path: true. A safety-path signal belongs "
            "in firmware/src/safety/ with its own generated table, not in the "
            "measurement layer (AGENTS.md section 5)."
        )
    if entry["class"] != REQUIRED_CLASS:
        raise SignalListError(
            f"signal {signal_id} has class {entry['class']!r}, expected {REQUIRED_CLASS!r}"
        )
    if entry["unit"] != REQUIRED_UNIT:
        raise SignalListError(
            f"signal {signal_id} has unit {entry['unit']!r}, expected {REQUIRED_UNIT!r}"
        )
    for field, expected in (
        ("device", REQUIRED_DEVICE),
        ("sensor", REQUIRED_SENSOR),
        ("wiring", REQUIRED_WIRING),
    ):
        if source.get(field) != expected:
            raise SignalListError(
                f"signal {signal_id} has source.{field} {source.get(field)!r}, "
                f"expected {expected!r}"
            )
    if source.get("chip_select") not in CHIP_SELECT_RANGE:
        raise SignalListError(
            f"signal {signal_id} has chip select {source.get('chip_select')!r}, "
            f"outside the {CHIP_SELECT_RANGE.start} to {CHIP_SELECT_RANGE.stop - 1} "
            "the MAX31865 is wired for"
        )
    if source.get("level") not in PRODUCT_LEVELS:
        raise SignalListError(
            f"signal {signal_id} has level {source.get('level')!r}, "
            f"which the firmware does not understand (known: {sorted(PRODUCT_LEVELS)})"
        )
    if source.get("orientation_deg") not in ORIENTATIONS_DEG:
        raise SignalListError(
            f"signal {signal_id} has orientation {source.get('orientation_deg')!r} "
            f"degrees, expected one of {list(ORIENTATIONS_DEG)}"
        )
    if not isinstance(entry["update_rate_ms"], int) or entry["update_rate_ms"] <= 0:
        raise SignalListError(f"signal {signal_id} has no positive update_rate_ms")

    _check_valid_range(signal_id, entry["valid_range"])


def _check_valid_range(signal_id: Any, valid_range: Any) -> None:
    if not isinstance(valid_range, list) or len(valid_range) != 2:
        raise SignalListError(f"signal {signal_id} needs a valid_range of two values")

    low, high = valid_range
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        raise SignalListError(f"signal {signal_id} has a non-numeric valid_range")
    if low >= high:
        raise SignalListError(
            f"signal {signal_id} has valid_range [{low}, {high}], which is empty or inverted"
        )


def _entry_to_macro(entry: dict[str, Any]) -> str:
    source = entry["source"]
    low, high = entry["valid_range"]

    return (
        "\tX({name}, {id}, {chip_select}, {level}, {orientation}, {rate}, "
        "{low:.1f}f, {high:.1f}f)".format(
            name=str(entry["name"]).upper(),
            id=int(entry["id"]),
            chip_select=int(source["chip_select"]),
            level=PRODUCT_LEVELS[source["level"]],
            orientation=int(source["orientation_deg"]),
            rate=int(entry["update_rate_ms"]),
            low=float(low),
            high=float(high),
        )
    )


def _check_unique(entries: list[dict[str, Any]]) -> None:
    for field, reader in (
        ("id", lambda entry: entry["id"]),
        ("chip select", lambda entry: (entry["source"] or {}).get("chip_select")),
    ):
        seen: dict[Any, Any] = {}
        for entry in entries:
            value = reader(entry)
            if value in seen:
                raise SignalListError(
                    f"signals {seen[value]} and {entry['id']} share {field} {value!r}; "
                    "each PT100 needs its own, or one sensor would be reported under "
                    "another's signal id"
                )
            seen[value] = entry["id"]


def _load_version(raw: dict[str, Any], source: Path) -> int:
    version = raw.get("version")
    if not isinstance(version, int):
        raise SignalListError(f"{source} does not declare an integer version")
    return version


def render_header(signals_path: Path, story: str = STORY) -> str:
    """Return the C header for the PT100 sensors ``story`` reads."""
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

    # Every entry is validated before any is compared, so a missing field is
    # reported as such rather than tripping over its own absence below.
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
        print(f"gen_temperature_signals: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
