from pathlib import Path
from typing import Any

import cbor2
import pytest

from tankapi.records import (
    DecodeError,
    GapRecord,
    Quality,
    ScanRecord,
    decode_message,
)

# Five records captured from the simulator (S-067 spec, "Test plan"): time not
# known for seq 0-2 and known from seq 3, signal 2001 faulted, 1001 out of range.
SIMULATOR_BATCH = bytes.fromhex(
    (Path(__file__).parent / "fixtures" / "simulator-batch-cbor-hex.txt").read_text()
)
BOOT = bytes(range(16))


def scan(**changes: Any) -> dict[str, Any]:
    record = {"v": 1, "dev": "DEV-1", "sl": 1, "boot": BOOT, "seq": 7, "up": 5000, "tk": False}
    record["r"] = [{"id": 1001, "val": 4200, "q": 0, "age": 20}]
    record.update(changes)
    return record


def gap(**changes: Any) -> dict[str, Any]:
    first = {"boot": BOOT, "seq": 3, "up": 3000, "tk": False}
    last = {"boot": BOOT, "seq": 9, "up": 9000, "tk": True, "t": 1_763_683_209}
    return {"v": 1, "dev": "DEV-1", "gap": {"lost": 7, "first": first, "last": last, **changes}}


def reading(**fields: Any) -> dict[str, Any]:
    return scan(r=[{"id": 2001, "q": 0, "age": 0, **fields}])


def test_simulator_batch_decodes_in_order_with_its_time_fields() -> None:
    records = decode_message(SIMULATOR_BATCH)

    assert [r.sequence for r in records] == [0, 1, 2, 3, 4]
    assert all(isinstance(r, ScanRecord) and r.device_id == "SIM-0001" for r in records)
    assert [r.time_known for r in records] == [False, False, False, True, True]
    assert [r.unix_time_s is None for r in records] == [True, True, True, False, False]
    assert all(len(r.readings) == 27 for r in records)


def test_faulted_reading_keeps_no_value_and_out_of_range_keeps_the_measured_one() -> None:
    readings = {x.signal_id: x for x in decode_message(SIMULATOR_BATCH)[0].readings}

    assert readings[2001].quality is Quality.FAULT and readings[2001].value is None
    assert readings[1001].quality is Quality.OUT_OF_RANGE and readings[1001].value == 21600
    assert all(x.age_ms >= 0 for x in readings.values())


def test_gap_record_and_scan_in_one_batch() -> None:
    lost, scanned = decode_message(cbor2.dumps([gap(), scan(tk=True, t=1_763_683_210)]))

    assert isinstance(lost, GapRecord) and lost.lost == 7 and lost.device_id == "DEV-1"
    assert (lost.first.sequence, lost.first.unix_time_s) == (3, None)
    assert (lost.last.sequence, lost.last.unix_time_s) == (9, 1_763_683_209)
    assert scanned.unix_time_s == 1_763_683_210
    assert scanned.readings[0].value == 4200


def test_bool_value_and_bytearray_payload() -> None:
    (record,) = decode_message(bytearray(cbor2.dumps([reading(val=True)])))

    assert record.readings[0].value is True


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (b"\x85\x01", "not valid CBOR"),
        (b"", "not valid CBOR"),
        (cbor2.dumps([scan()]) + b"\x00", "1 bytes follow the CBOR item"),
        (cbor2.dumps(scan()), "expected a batch array, got dict"),
        (cbor2.dumps([]), "1 to 5 records, got 0"),
        (cbor2.dumps([scan()] * 6), "1 to 5 records, got 6"),
    ],
)
def test_malformed_message_is_refused(payload: bytes, reason: str) -> None:
    with pytest.raises(DecodeError, match=reason) as caught:
        decode_message(payload)

    assert caught.value.record_index is None


def test_payload_must_be_bytes() -> None:
    with pytest.raises(DecodeError, match="payload must be bytes, got str"):
        decode_message("[]")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("record", "reason"),
    [
        ("text", "expected a map, got str"),
        (scan(v=2), "unknown record version 2"),
        (scan(v=True), "unknown record version True"),
        ({"v": 1, "dev": "DEV-1"}, "neither a scan record"),
        ({k: v for k, v in scan().items() if k != "seq"}, "missing field 'seq'"),
        (scan(extra=1), "unknown field 'extra'"),
        (scan(r=[]), "non-empty array"),
        (scan(seq=-1), "'seq' must be an unsigned integer"),
        (scan(up=True), "'up' must be an unsigned integer"),
        (scan(boot=b"short"), "'boot' must be 16 bytes"),
        (scan(dev=""), "'dev' must be text"),
        (scan(dev="x" * 65), "'dev' must be text"),
        (scan(tk="yes"), "'tk' must be a bool"),
        (scan(tk=True), "time known"),
        (scan(t=1), "time not known"),
        (reading(), "signal 2001\\): quality good must carry a value"),
        (reading(q=3, val=0), "quality fault must carry no value"),
        (reading(q=4, val=0), "quality unconfigured must carry no value"),
        (reading(q=9, val=0), "unknown quality 9"),
        (reading(val=1.5), "'val' must be an integer or a bool"),
        (scan(r=[5]), "reading 0 must be a map"),
        (gap(lost=0), "'lost' must be at least 1"),
        (gap(first="x"), "'gap.first' must be a map"),
        (gap(extra=1), "'gap': unknown field 'extra'"),
    ],
)
def test_malformed_record_names_the_record_and_the_reason(record: Any, reason: str) -> None:
    with pytest.raises(DecodeError, match=reason) as caught:
        decode_message(cbor2.dumps([scan(), record]))

    assert caught.value.record_index == 1
    assert str(caught.value).startswith("record 1: ")
