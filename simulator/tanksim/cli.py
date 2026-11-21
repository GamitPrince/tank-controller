"""The one command that starts the simulator.

    python -m tanksim                # or: tanksim

With no arguments it loads ``interfaces/signals-v1.yaml``, runs a short burst of
scans with no hardware and writes a human-readable summary, so a newcomer can
see every Phase 1 signal immediately. ``--output`` writes the framed bytes a
consumer actually reads.

``[Confirm]`` The spec left open whether the simulator emulates the FRDM's UART
framed protocol or the ESP32's MQTT publish. This implements the FRDM side: CBOR
records in COBS frames with a sequence number and a CRC (ADR-0004 decisions 5
and 6), written to a byte stream. That is the side both the other halves depend
on, it needs no broker, no certificates and no cloud account, and ADR-0007's
three gates have not been passed, so nothing here may open one. An MQTT
publisher is a thin wrapper over the same frames and belongs with the cloud
stories (P1-14, P1-15).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import BinaryIO, TextIO

from .cddl import load_schema
from .clock import SimClock
from .device import ScanResult, SimulatedDevice
from .faults import FaultPlan, load_scenario, parse_link_drop, parse_signal_fault
from .link import BufferedLink, RecordingSink, StreamSink
from .plant import PlantModel
from .record import Quality
from .replay import load_capture, replay
from .signals import load_signal_list

#: Defaults chosen so the bare command does something useful and finishes.
DEFAULT_DEVICE_ID = "SIM-0001"
DEFAULT_SCANS = 10
DEFAULT_INTERVAL_MS = 1000
#: A fixed boot time, so two runs of the bare command produce the same records.
DEFAULT_BOOT_UNIX_S = 1763683200  # 2025-11-21T00:00:00Z


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(
        prog="tanksim",
        description=(
            "Tank-AI Phase 1 simulator: produces every signal in "
            "interfaces/signals-v1.yaml as CBOR records in the framed link "
            "protocol, with no hardware. Read-only monitoring only."
        ),
    )
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID, help="device id to publish under")
    parser.add_argument(
        "--signals", type=Path, default=None, help="signal list to load (default: interfaces/)"
    )
    parser.add_argument(
        "--scans", type=int, default=DEFAULT_SCANS, help="how many scans to run (0 means none)"
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=DEFAULT_INTERVAL_MS,
        help="simulated milliseconds between scans",
    )
    parser.add_argument(
        "--boot-unix-s",
        type=int,
        default=DEFAULT_BOOT_UNIX_S,
        help="wall-clock time at boot, which SNTP reveals",
    )
    parser.add_argument(
        "--sntp-sync-after-ms",
        type=int,
        default=0,
        help="uptime at which the clock becomes known; before it, records carry no Unix time",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the framed byte stream to this file as well as summarising it",
    )
    parser.add_argument(
        "--fault",
        action="append",
        default=[],
        metavar="ID:KIND[@FIRST-LAST]",
        help="inject a fault, e.g. 2001:sensor_fault or 1001:out_of_range@3-6",
    )
    parser.add_argument(
        "--link-drop",
        action="append",
        default=[],
        metavar="FIRST-LAST",
        help="drop the link for these scans; buffered records replay with original timestamps",
    )
    parser.add_argument(
        "--scenario", type=Path, default=None, help="read faults and link drops from a JSON file"
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        metavar="CAPTURE",
        help="replay a capture instead of simulating, keeping its original timestamps",
    )
    return parser


def _plan_from(args: argparse.Namespace) -> FaultPlan:
    if args.scenario is not None:
        plan = load_scenario(args.scenario)
        if args.fault or args.link_drop:
            plan = FaultPlan(
                signal_faults=plan.signal_faults
                + tuple(parse_signal_fault(spec) for spec in args.fault),
                link_drops=plan.link_drops
                + tuple(parse_link_drop(spec) for spec in args.link_drop),
            )
        return plan
    return FaultPlan(
        signal_faults=tuple(parse_signal_fault(spec) for spec in args.fault),
        link_drops=tuple(parse_link_drop(spec) for spec in args.link_drop),
    )


def _summarise(
    results: list[ScanResult], quality: Quality, out: TextIO, signal_names: dict[int, str]
) -> None:
    for result in results:
        record = result.record
        when = "time not yet known" if not record.time_known else f"t={record.unix_time_s}"
        out.write(
            f"scan seq={record.sequence} up={record.uptime_ms}ms {when} "
            f"readings={len(record.readings)} "
            f"{'delivered' if result.delivered else 'buffered'}"
            f"{f' replayed={result.replayed}' if result.replayed else ''}\n"
        )
        for reading in record.readings:
            if reading.quality == quality.good:
                continue
            name = signal_names.get(reading.signal_id, "?")
            out.write(
                f"    {reading.signal_id} {name}: q={reading.quality} "
                f"value={'absent' if reading.value is None else reading.value}\n"
            )


def _run_replay(args: argparse.Namespace, out: TextIO) -> int:
    captured = load_capture(args.replay, load_schema())
    sink = RecordingSink()
    count = replay(captured, sink)
    out.write(f"replayed {count} record(s) from {args.replay}, timestamps unchanged\n")
    for delivery in sink.deliveries:
        out.write(f"    up={delivery.uptime_ms}ms t={delivery.unix_time_s}\n")
    return 0


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    """Entry point. Returns the process exit status."""
    args = build_parser().parse_args(argv)
    out = out or sys.stdout

    if args.replay is not None:
        return _run_replay(args, out)

    signal_list = load_signal_list(args.signals)
    schema = load_schema()
    plan = _plan_from(args)

    output_file: BinaryIO | None = None
    try:
        if args.output is not None:
            output_file = args.output.open("wb")
            sink = StreamSink(output_file)
        else:
            sink = RecordingSink()

        link = BufferedLink(sink)
        device = SimulatedDevice(
            device_id=args.device_id,
            signal_list=signal_list,
            link=link,
            clock=SimClock(
                boot_unix_s=args.boot_unix_s, sntp_sync_after_ms=args.sntp_sync_after_ms
            ),
            plant=PlantModel(signal_list),
            fault_plan=plan,
            schema=schema,
        )
        out.write(
            f"tanksim: device {device.device_id}, signal list v{signal_list.version} "
            f"({len(signal_list)} signals, {len(signal_list.safety_path_signals())} of them "
            f"safety-chain or alarm status inputs), read-only\n"
        )
        results = device.run(args.scans, args.interval_ms)
        _summarise(results, Quality(schema), out, {s.id: s.name for s in signal_list})
        if link.buffered:
            out.write(f"{link.buffered} record(s) still held in the outage buffer\n")
        if args.output is not None:
            out.write(f"wrote the framed stream to {args.output}\n")
    finally:
        if output_file is not None:
            output_file.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
