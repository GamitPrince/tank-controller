"""Tests for replaying a capture without restamping it."""

from __future__ import annotations

import io

import pytest

from tanksim.framing import encode_frame
from tanksim.link import RecordingSink, StreamSink
from tanksim.replay import ReplayError, load_capture, read_capture, replay


@pytest.fixture
def capture(make_device, schema) -> bytes:
    """A capture of four scans, the middle two taken during an outage."""
    from tanksim.faults import FaultPlan, LinkDrop, ScanWindow
    from tanksim.link import BufferedLink

    stream = io.BytesIO()
    link = BufferedLink(StreamSink(stream))
    plan = FaultPlan(link_drops=(LinkDrop(ScanWindow(1, 2)),))
    make_device(link, plan, 0).run(scans=4, interval_ms=1000)
    return stream.getvalue()


def test_a_capture_reads_back_as_valid_records(capture, schema, device_id):
    captured = read_capture(capture, schema)
    assert [item.sequence for item in captured] == [0, 1, 2, 3]
    assert all(item.record["dev"] == device_id for item in captured)


def test_replay_keeps_the_original_timestamps(capture, schema):
    captured = read_capture(capture, schema)
    sink = RecordingSink()
    assert replay(captured, sink) == 4

    # The timestamps are the ones the device wrote, not the moment of replay,
    # and the frames are byte-identical to the captured ones.
    assert [d.uptime_ms for d in sink.deliveries] == [0, 1000, 2000, 3000]
    assert [d.unix_time_s for d in sink.deliveries] == [item.unix_time_s for item in captured]
    assert sink.frames == [item.frame for item in captured]
    assert all(d.replayed for d in sink.deliveries)


def test_replaying_a_capture_taken_before_sntp_keeps_no_unix_time(make_device, schema):
    from tanksim.link import BufferedLink

    stream = io.BytesIO()
    make_device(BufferedLink(StreamSink(stream)), None, 1500).run(scans=2, interval_ms=1000)
    captured = read_capture(stream.getvalue(), schema)
    assert [item.unix_time_s for item in captured] == [None, None]


def test_a_capture_file_is_read(tmp_path, capture, schema):
    path = tmp_path / "capture.bin"
    path.write_bytes(capture)
    assert len(load_capture(path, schema)) == 4


def test_a_missing_capture_file_is_refused(tmp_path):
    with pytest.raises(ReplayError, match="not found"):
        load_capture(tmp_path / "nothing.bin")


def test_an_empty_capture_is_refused():
    with pytest.raises(ReplayError, match="no frames"):
        read_capture(b"")


def test_a_capture_that_is_not_a_record_is_refused(schema):
    stream = encode_frame(0, b"\xa1\x61a\x01")  # valid CBOR, not a record
    with pytest.raises(ReplayError, match="does not match the schema"):
        read_capture(stream, schema)


def test_a_corrupt_frame_in_a_capture_is_refused(capture, schema):
    corrupt = bytearray(capture)
    corrupt[10] ^= 0xFF
    with pytest.raises(ValueError):
        read_capture(bytes(corrupt), schema)
