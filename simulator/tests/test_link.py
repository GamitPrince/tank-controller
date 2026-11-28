"""Tests for the link, its outage buffer and the replay that keeps timestamps."""

from __future__ import annotations

import io

import pytest

from tanksim.link import BufferedLink, Delivery, FanOutSink, LinkError, RecordingSink, StreamSink


def test_a_frame_goes_straight_out_while_the_link_is_up(sink):
    link = BufferedLink(sink)
    assert link.publish(b"frame", uptime_ms=1000, unix_time_s=10) is True
    assert sink.frames == [b"frame"]
    assert link.buffered == 0
    assert sink.deliveries[0].replayed is False


def test_frames_are_buffered_while_the_link_is_down(sink):
    link = BufferedLink(sink)
    link.set_up(False)
    assert link.publish(b"one", 1000, 10) is False
    assert link.publish(b"two", 2000, 20) is False
    assert sink.frames == []
    assert link.buffered == 2
    assert link.up is False


def test_the_buffer_replays_with_the_original_timestamps(sink):
    link = BufferedLink(sink)
    link.set_up(False)
    link.publish(b"one", uptime_ms=1000, unix_time_s=10)
    link.publish(b"two", uptime_ms=2000, unix_time_s=20)

    assert link.set_up(True) == 2

    # The timestamps are the scans' own, not the moment of the flush, and the
    # order is preserved. A consumer that stamped arrival time would show
    # buffered data as live.
    assert [(d.uptime_ms, d.unix_time_s) for d in sink.deliveries] == [(1000, 10), (2000, 20)]
    assert all(d.replayed for d in sink.deliveries)
    assert link.buffered == 0


def test_a_record_buffered_before_the_clock_was_known_keeps_no_unix_time(sink):
    link = BufferedLink(sink)
    link.set_up(False)
    link.publish(b"early", uptime_ms=500, unix_time_s=None)
    link.set_up(True)
    assert sink.deliveries[0].unix_time_s is None


def test_bringing_an_up_link_up_again_replays_nothing(sink):
    link = BufferedLink(sink)
    assert link.set_up(True) == 0


def test_a_full_buffer_drops_the_record_it_cannot_write(sink):
    link = BufferedLink(sink, capacity=2)
    link.set_up(False)
    for index in range(4):
        link.publish(f"frame-{index}".encode(), index * 1000, None)

    assert link.buffered == 2
    assert link.dropped == 2
    assert link.buffer_fraction == 1.0

    link.set_up(True)
    # An append-only log keeps the history it already wrote; the records that
    # could not be appended are the ones lost.
    assert sink.frames == [b"frame-0", b"frame-1"]


def test_the_buffer_fraction_tracks_the_fill(sink):
    link = BufferedLink(sink, capacity=4)
    link.set_up(False)
    link.publish(b"one", 0, None)
    assert link.buffer_fraction == pytest.approx(0.25)
    assert link.capacity == 4


def test_a_capacity_below_one_is_refused(sink):
    with pytest.raises(LinkError, match="at least 1"):
        BufferedLink(sink, capacity=0)


def test_a_stream_sink_writes_the_raw_frames():
    stream = io.BytesIO()
    sink = StreamSink(stream)
    sink.deliver(Delivery(frame=b"abc", uptime_ms=0, unix_time_s=None))
    sink.deliver(Delivery(frame=b"def", uptime_ms=1, unix_time_s=None))
    assert stream.getvalue() == b"abcdef"


def test_a_recording_sink_keeps_every_delivery():
    sink = RecordingSink()
    sink.deliver(Delivery(frame=b"x", uptime_ms=1, unix_time_s=None))
    assert len(sink.deliveries) == 1


def test_a_fan_out_sink_hands_each_delivery_to_every_sink():
    first, second = RecordingSink(), RecordingSink()
    FanOutSink(first, second).deliver(Delivery(frame=b"x", uptime_ms=0, unix_time_s=None))
    assert first.frames == second.frames == [b"x"]
