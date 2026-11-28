"""Tests for batch messages (S-095): what one MQTT message holds."""

from __future__ import annotations

import cbor2
import pytest

from tanksim.batch import (
    CUT_CHANGE,
    CUT_END,
    CUT_FULL,
    MAX_BATCH_MESSAGES,
    Batch,
    BatchError,
    BatchSink,
    contact_ids,
    is_prompt_change,
)
from tanksim.faults import FaultPlan, parse_link_drop, parse_signal_fault
from tanksim.framing import encode_frame
from tanksim.gap import gap_frame
from tanksim.link import BufferedLink, Delivery

CONTACT, ANALOGUE = 3001, 1001


def scan(contact=True, level=4200, quality=0, ids=(ANALOGUE, CONTACT)) -> dict:
    readings = {
        ANALOGUE: {"id": ANALOGUE, "val": level, "q": quality, "age": 2},
        CONTACT: {"id": CONTACT, "val": contact, "q": 0, "age": 1},
    }
    return {"r": [readings[i] for i in ids]}


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        (None, scan(), False),
        (scan(), scan(level=4300), False),
        (scan(), scan(contact=False), True),
        (scan(), scan(quality=2), True),
        (scan(), {"r": [{"id": ANALOGUE, "q": 0, "age": 2}, scan()["r"][1]]}, True),
        (scan(), scan(ids=(CONTACT, ANALOGUE)), True),
        (scan(), scan(ids=(ANALOGUE,)), True),
    ],
    ids=["first", "analogue", "contact", "quality", "value-gone", "reordered", "shorter"],
)
def test_the_prompt_change_rule_follows_s065(previous, current, expected):
    assert is_prompt_change(previous, current, frozenset({CONTACT})) is expected


@pytest.fixture
def batches() -> list[Batch]:
    return []


@pytest.fixture
def run(make_device, signal_list, schema, batches):
    """Run the simulated device into a batch sink and return its batches."""

    def go(scans: int, plan: FaultPlan | None = None, capacity: int = 1024):
        sink = BatchSink(batches.append, contact_ids(signal_list), schema)
        link = BufferedLink(sink, capacity, lambda a, b, n: gap_frame(a, b, n, schema))
        results = make_device(link, plan, sntp_sync_after_ms=2500).run(scans, 1000)
        sink.close()
        return results

    return go


def decoded(batch: Batch, schema) -> list[dict]:
    messages = cbor2.loads(batch.payload)
    schema.validate(messages, "batch")
    assert batch.count == len(messages) <= MAX_BATCH_MESSAGES
    return messages


def test_steady_scans_go_five_to_a_batch_with_a_short_last_one(run, batches, schema):
    run(12)
    assert [(b.count, b.cut) for b in batches] == [(5, CUT_FULL), (5, CUT_FULL), (2, CUT_END)]
    sequences = [m["seq"] for b in batches for m in decoded(b, schema)]
    assert sequences == list(range(12))


def test_a_quality_change_sends_its_batch_at_once(run, batches, schema):
    run(9, FaultPlan(signal_faults=(parse_signal_fault("2001:sensor_fault@2-8"),)))
    assert [(b.count, b.cut) for b in batches] == [(3, CUT_CHANGE), (5, CUT_FULL), (1, CUT_END)]
    assert decoded(batches[0], schema)[-1]["seq"] == 2


def test_a_backlog_replays_oldest_first_with_its_original_timestamps(run, batches, schema):
    # A fault starting inside the outage changes quality, but the backlog
    # still drains five to a batch, as S-063's poll does.
    plan = FaultPlan(
        signal_faults=(parse_signal_fault("2001:sensor_fault@4-9"),),
        link_drops=(parse_link_drop("1-7"),),
    )
    results = run(10, plan)
    assert [(b.count, b.cut) for b in batches] == [(5, CUT_FULL), (5, CUT_FULL)]
    messages = [m for b in batches for m in decoded(b, schema)]
    assert [m["seq"] for m in messages] == list(range(10))
    for message, result in zip(messages, results, strict=True):
        assert message["up"] == result.record.uptime_ms
        assert message.get("t") == result.record.unix_time_s
    assert messages[1]["tk"] is False and messages[3]["tk"] is True


def test_scans_the_buffer_lost_arrive_as_a_gap_record_in_a_batch(run, batches, schema):
    run(8, FaultPlan(link_drops=(parse_link_drop("1-5"),)), capacity=2)
    first, second = (decoded(b, schema) for b in batches)
    assert [m.get("seq") for m in first] == [0, 1, 2, None, 6]
    gap = first[3]["gap"]
    assert (gap["lost"], gap["first"]["seq"], gap["last"]["seq"]) == (3, 3, 5)
    assert [m["seq"] for m in second] == [7]


@pytest.mark.parametrize("size", [0, MAX_BATCH_MESSAGES + 1])
def test_a_batch_limit_outside_one_to_five_is_refused(size):
    with pytest.raises(BatchError, match="1 to 5"):
        BatchSink(lambda batch: None, [], max_messages=size)


def test_a_smaller_batch_limit_is_honoured(make_device, signal_list, schema, batches):
    sink = BatchSink(batches.append, [], schema, max_messages=2)
    make_device(BufferedLink(sink)).run(5, 1000)
    sink.close()
    assert [b.count for b in batches] == [2, 2, 1]


def test_closing_an_empty_sink_sends_nothing(batches):
    sink = BatchSink(batches.append, [])
    sink.close()
    assert batches == []


def test_a_gap_record_counts_as_one_message_and_never_cuts(make_device, signal_list, schema):
    batches: list[Batch] = []
    sink = BatchSink(batches.append, contact_ids(signal_list), schema)
    results = make_device(BufferedLink(sink)).run(2, 1000)
    lost = {key: results[1].record.to_record_map()[key] for key in ("boot", "seq", "up", "tk")}
    gap = {
        "v": 1,
        "dev": results[0].record.device_id,
        "gap": {"lost": 1, "first": lost, "last": lost},
    }
    sink.deliver(Delivery(encode_frame(2, cbor2.dumps(gap)), 0, None, replayed=True))
    sink.close()
    assert [(b.count, b.cut) for b in batches] == [(3, CUT_END)]
    assert "gap" in decoded(batches[0], schema)[2]
