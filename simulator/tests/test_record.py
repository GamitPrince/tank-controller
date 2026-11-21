"""Tests for building, encoding and decoding the CBOR scan record."""

from __future__ import annotations

import cbor2
import pytest

from tanksim.record import (
    BOOT_ID_BYTES,
    Reading,
    RecordError,
    ScanRecord,
    decode,
    default_schema,
)

BOOT_ID = bytes(range(BOOT_ID_BYTES))


def make_record(**changes) -> ScanRecord:
    fields = {
        "device_id": "SIM-0001",
        "signal_list_version": 1,
        "boot_id": BOOT_ID,
        "sequence": 0,
        "uptime_ms": 1000,
        "time_known": True,
        "unix_time_s": 1763683200,
        "readings": (Reading(signal_id=1001, quality=0, age_ms=5, value=12000),),
    }
    fields.update(changes)
    return ScanRecord(**fields)


def test_the_quality_codes_come_from_the_schema(quality):
    assert (quality.good, quality.stale, quality.out_of_range) == (0, 1, 2)
    assert (quality.fault, quality.unconfigured) == (3, 4)
    assert quality.codes_without_value == frozenset({3, 4})


def test_a_quality_the_schema_does_not_define_is_refused(quality):
    with pytest.raises(RecordError, match="no quality named"):
        quality["invented"]


def test_the_default_schema_is_shared(schema):
    assert default_schema().source == schema.source


def test_a_record_encodes_and_decodes(schema):
    payload = make_record().encode(schema)
    decoded = decode(payload, schema)
    assert decoded["dev"] == "SIM-0001"
    assert decoded["boot"] == BOOT_ID
    assert decoded["r"][0] == {"id": 1001, "q": 0, "age": 5, "val": 12000}


def test_a_faulty_reading_carries_no_value(schema, quality):
    record = make_record(readings=(Reading(signal_id=2001, quality=quality.fault, age_ms=3),))
    decoded = decode(record.encode(schema), schema)
    # A failed sensor is flagged and excluded, never silently replaced.
    assert "val" not in decoded["r"][0]
    assert decoded["r"][0]["q"] == quality.fault


def test_a_record_without_a_known_time_omits_the_unix_time(schema):
    record = make_record(time_known=False, unix_time_s=None)
    decoded = decode(record.encode(schema), schema)
    assert decoded["tk"] is False
    assert "t" not in decoded


def test_a_boot_id_of_the_wrong_length_is_refused():
    with pytest.raises(RecordError, match="boot id must be 16 bytes"):
        make_record(boot_id=b"short")


def test_a_record_with_no_readings_is_refused():
    with pytest.raises(RecordError, match="at least one reading"):
        make_record(readings=())


def test_a_known_time_without_a_timestamp_is_refused():
    with pytest.raises(RecordError, match="no Unix time was given"):
        make_record(time_known=True, unix_time_s=None)


def test_a_timestamp_without_a_known_time_is_refused():
    with pytest.raises(RecordError, match="while time_known is false"):
        make_record(time_known=False, unix_time_s=1763683200)


def test_a_negative_age_is_refused(schema):
    record = make_record(readings=(Reading(signal_id=1, quality=0, age_ms=-1, value=0),))
    with pytest.raises(RecordError, match="negative age"):
        record.encode(schema)


def test_encoding_refuses_a_record_the_schema_forbids(schema):
    # The guard that matters: the simulator cannot emit a record the contract
    # in interfaces/ does not allow.
    record = make_record(signal_list_version=-1)
    with pytest.raises(ValueError, match="expected uint"):
        record.encode(schema)


def test_decoding_refuses_a_payload_the_schema_forbids(schema):
    payload = cbor2.dumps({"v": 1, "dev": "x"})
    with pytest.raises(ValueError, match="required member"):
        decode(payload, schema)
