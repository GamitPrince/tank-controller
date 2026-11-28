"""Tests for the one command that starts the simulator."""

from __future__ import annotations

import io
import json

import cbor2
import pytest

from tanksim.cli import build_parser, main
from tanksim.faults import FaultError
from tanksim.framing import decode_frame, split_frames
from tanksim.record import decode


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    status = main(list(argv), out=out)
    return status, out.getvalue()


def test_the_bare_command_runs_with_no_hardware():
    # "Starts from one command with no hardware", the story's third criterion.
    status, output = run()
    assert status == 0
    assert "read-only" in output
    assert output.count("scan seq=") == 10


def test_the_banner_counts_the_signals_in_the_list(signal_list):
    _, output = run("--scans", "1")
    assert f"{len(signal_list)} signals" in output
    assert f"{len(signal_list.safety_path_signals())} of them" in output


def test_zero_scans_is_allowed():
    status, output = run("--scans", "0")
    assert status == 0
    assert "scan seq=" not in output


def test_the_framed_stream_is_written_and_decodes(tmp_path, schema, signal_list):
    path = tmp_path / "capture.bin"
    status, output = run("--scans", "2", "--output", str(path))
    assert status == 0
    assert str(path) in output

    frames = split_frames(path.read_bytes())
    assert len(frames) == 2
    for index, raw in enumerate(frames):
        frame = decode_frame(raw)
        assert frame.sequence == index
        record = decode(frame.payload, schema)
        assert len(record["r"]) == len(signal_list)


def test_a_fault_flag_shows_up_in_the_summary(signal_list, quality):
    temperature = signal_list.in_group("temperature")[0]
    _, output = run("--scans", "1", "--fault", f"{temperature.id}:sensor_fault")
    assert f"{temperature.id} {temperature.name}: q={quality.fault} value=absent" in output


def test_an_out_of_range_flag_shows_up_in_the_summary(signal_list, quality):
    analogue = signal_list.in_group("analogue")[0]
    _, output = run("--scans", "1", "--fault", f"{analogue.id}:out_of_range")
    assert f"q={quality.out_of_range}" in output


def test_a_link_drop_flag_buffers_and_replays():
    _, output = run("--scans", "4", "--link-drop", "1-2")
    assert "buffered" in output
    assert "replayed=2" in output


def test_a_link_drop_still_running_at_the_end_is_reported():
    _, output = run("--scans", "3", "--link-drop", "1-")
    assert "still held in the outage buffer" in output


def test_records_before_sntp_say_the_time_is_not_known():
    _, output = run("--scans", "2", "--interval-ms", "1000", "--sntp-sync-after-ms", "1500")
    assert "time not yet known" in output


def test_a_scenario_file_is_used(tmp_path, signal_list, quality):
    temperature = signal_list.in_group("temperature")[0]
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps(
            {
                "signal_faults": [
                    {"signal_id": temperature.id, "kind": "sensor_fault", "first_scan": 0}
                ]
            }
        ),
        encoding="utf-8",
    )
    _, output = run("--scans", "1", "--scenario", str(path))
    assert f"{temperature.id} {temperature.name}: q={quality.fault}" in output


def test_a_scenario_file_and_flags_combine(tmp_path, signal_list):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"link_drops": [{"first_scan": 1, "last_scan": 1}]}), "utf-8")
    analogue = signal_list.in_group("analogue")[0]
    _, output = run(
        "--scans", "3", "--scenario", str(path), "--fault", f"{analogue.id}:out_of_range@0"
    )
    assert "buffered" in output
    assert f"{analogue.id} {analogue.name}" in output


def test_a_fault_on_an_unknown_signal_stops_the_run():
    with pytest.raises(Exception, match="no signal with id 9999"):
        run("--scans", "1", "--fault", "9999:sensor_fault")


def test_a_malformed_fault_flag_stops_the_run():
    with pytest.raises(FaultError):
        run("--scans", "1", "--fault", "nonsense")


def test_a_capture_can_be_replayed(tmp_path):
    path = tmp_path / "capture.bin"
    run("--scans", "3", "--link-drop", "1-1", "--output", str(path))
    status, output = run("--replay", str(path))
    assert status == 0
    assert "replayed 3 record(s)" in output
    assert "timestamps unchanged" in output
    assert "up=0ms" in output and "up=2000ms" in output


def test_a_custom_device_id_is_used(tmp_path, schema):
    path = tmp_path / "capture.bin"
    run("--scans", "1", "--device-id", "SIM-ABC", "--output", str(path))
    frame = decode_frame(split_frames(path.read_bytes())[0])
    assert decode(frame.payload, schema)["dev"] == "SIM-ABC"


def test_an_explicit_signal_list_is_used(interfaces_dir):
    _, output = run("--scans", "1", "--signals", str(interfaces_dir / "signals-v1.yaml"))
    assert "signal list v1" in output


def test_the_parser_documents_the_read_only_scope():
    assert "Read-only" in build_parser().description


def batch_lines(path) -> list[list[dict]]:
    lines = path.read_text().splitlines()
    return [cbor2.loads(bytes.fromhex(line)) for line in lines]


def test_batches_are_written_one_hex_line_each(tmp_path, schema):
    path = tmp_path / "batches.txt"
    status, output = run("--scans", "7", "--batches", str(path))
    assert status == 0
    assert "wrote 2 batch message(s)" in output
    assert path.read_bytes().count(b"\r") == 0
    batches = batch_lines(path)
    for batch in batches:
        schema.validate(batch, "batch")
    assert [[m["seq"] for m in batch] for batch in batches] == [[0, 1, 2, 3, 4], [5, 6]]


def test_a_capture_can_be_replayed_into_batches(tmp_path, schema):
    capture, path = tmp_path / "capture.bin", tmp_path / "batches.txt"
    run("--scans", "6", "--output", str(capture))
    status, output = run("--replay", str(capture), "--batches", str(path))
    assert status == 0
    assert "cut by full" in output and "cut by end" in output
    records = [m for batch in batch_lines(path) for m in batch]
    originals = [
        decode(decode_frame(raw).payload, schema) for raw in split_frames(capture.read_bytes())
    ]
    assert records == originals
