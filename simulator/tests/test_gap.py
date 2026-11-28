"""Tests for the gap record of scans the outage buffer dropped (S-095, S-040)."""

from __future__ import annotations

import io

from tanksim.faults import FaultPlan, parse_link_drop
from tanksim.framing import decode_frame
from tanksim.gap import gap_frame
from tanksim.link import BufferedLink, RecordingSink, StreamSink
from tanksim.record import decode

OUTAGE = FaultPlan(link_drops=(parse_link_drop("0-2"),))


def test_a_gap_frame_carries_the_time_fields_of_its_two_ends(make_device, schema, device_id):
    results = make_device(BufferedLink(RecordingSink()), sntp_sync_after_ms=1500).run(3, 1000)
    frame = gap_frame(results[0].frame, results[2].frame, 3, schema)

    decoded = decode_frame(frame)
    assert decoded.sequence == 2
    record = decode(decoded.payload, schema)
    schema.validate(record, "gap-record")
    assert record["dev"] == device_id
    first, last = record["gap"]["first"], record["gap"]["last"]
    assert (record["gap"]["lost"], first["seq"], last["seq"]) == (3, 0, 2)
    assert first["tk"] is False and "t" not in first
    assert last["t"] == results[2].record.unix_time_s


def test_a_gap_is_reported_once_per_outage(make_device, schema):
    sink = RecordingSink()
    link = BufferedLink(sink, capacity=1, gap_frame=lambda a, b, n: gap_frame(a, b, n, schema))
    make_device(link, OUTAGE).run(3, 1000)
    assert link.set_up(True) == 2
    link.set_up(False)
    assert link.set_up(True) == 0
    assert len(sink.deliveries) == 2
    gap = decode(decode_frame(sink.frames[1]).payload, schema)["gap"]
    assert gap["lost"] == 2 and sink.deliveries[1].replayed


def test_without_a_builder_lost_scans_are_only_counted(make_device):
    link = BufferedLink(StreamSink(io.BytesIO()), capacity=1)
    make_device(link, OUTAGE).run(3, 1000)
    assert link.set_up(True) == 1
    assert link.dropped == 2
