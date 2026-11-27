from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from tankapi.db import AuditRow, GapRow, ReadingRow, ScanRow
from tankapi.records import GapRecord, LostScan, Quality, Reading, ScanRecord, decode_message

# The S-067 fixture: five simulator scans, time known from seq 3, 2001 faulted,
# 1001 out of range, and the digital inputs as bools.
SIMULATOR_BATCH = bytes.fromhex(
    (Path(__file__).parent / "fixtures" / "simulator-batch-cbor-hex.txt").read_text()
)
BOOT = bytes(range(16))
# The two marks of a gap may come from different boots (records.cddl).
GAP = GapRecord(
    device_id="DEV-1",
    lost=7,
    first=LostScan(BOOT, sequence=3, uptime_ms=3000, time_known=False, unix_time_s=None),
    last=LostScan(bytes(16), sequence=9, uptime_ms=900, time_known=True, unix_time_s=1_763_683_209),
)


def store(engine: Engine, *rows: object) -> None:
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


def scan(**changes: object) -> ScanRecord:
    reading = Reading(1001, Quality.GOOD, 20, 4200)
    record = ScanRecord("DEV-1", 1, BOOT, 7, 5000, False, None, (reading,))
    return replace(record, **changes)


def value_types(batch: tuple[ScanRecord, ...]) -> list[type]:
    return [type(x.value) for record in batch for x in record.readings]


def test_simulator_batch_round_trips_without_loss(engine: Engine) -> None:
    records = decode_message(SIMULATOR_BATCH)
    store(engine, *(ScanRow.from_record(r) for r in records))

    with Session(engine) as session:
        rows = session.scalars(select(ScanRow).order_by(ScanRow.sequence)).all()
        stored = tuple(row.to_record() for row in rows)

    assert stored == records
    # True == 1 in Python, so compare the value types too: a bool must come back a bool.
    assert value_types(stored) == value_types(records)
    assert set(value_types(stored)) == {int, bool, type(None)}


def test_faulted_reading_is_stored_with_no_value(engine: Engine) -> None:
    store(engine, ScanRow.from_record(decode_message(SIMULATOR_BATCH)[0]))

    with Session(engine) as session:
        faulted = session.scalars(select(ReadingRow).where(ReadingRow.signal_id == 2001)).one()

    assert faulted.quality == Quality.FAULT
    assert (faulted.value_int, faulted.value_bool) == (None, None)


def test_same_device_boot_and_sequence_is_refused(engine: Engine) -> None:
    store(engine, ScanRow.from_record(scan()))

    with pytest.raises(IntegrityError, match="UNIQUE"):
        store(engine, ScanRow.from_record(scan(uptime_ms=6000)))
    store(engine, ScanRow.from_record(scan(sequence=8)), ScanRow.from_record(scan(device_id="X")))


@pytest.mark.parametrize(
    ("quality", "value_int", "value_bool"),
    [
        (Quality.FAULT, 0, None),
        (Quality.UNCONFIGURED, None, False),
        (Quality.GOOD, None, None),
        (Quality.STALE, 1, True),
        (5, 1, None),
    ],
)
def test_value_that_does_not_match_the_quality_is_refused(
    engine: Engine, quality: int, value_int: int | None, value_bool: bool | None
) -> None:
    row = ScanRow.from_record(scan())
    row.readings[0].quality, row.readings[0].value_int = quality, value_int
    row.readings[0].value_bool = value_bool

    with pytest.raises(IntegrityError, match="CHECK"):
        store(engine, row)


@pytest.mark.parametrize(
    "changes",
    [
        {"time_known": True},
        {"unix_time_s": 1_763_683_209},
        {"boot_id": bytes(15)},
        {"device_id": ""},
        {"sequence": -1},
    ],
)
def test_scan_breaking_the_decoder_rules_is_refused(engine: Engine, changes: dict) -> None:
    with pytest.raises(IntegrityError, match="CHECK"):
        store(engine, ScanRow.from_record(scan(**changes)))


def test_gap_record_round_trips_with_both_marks(engine: Engine) -> None:
    store(engine, GapRow.from_record(GAP))

    with Session(engine) as session:
        assert session.scalars(select(GapRow)).one().to_record() == GAP


@pytest.mark.parametrize(
    "changes",
    [
        {"lost": 0},
        {"device_id": ""},
        {"first": replace(GAP.first, time_known=True)},
        {"last": replace(GAP.last, unix_time_s=None)},
        {"first": replace(GAP.first, boot_id=bytes(17))},
        {"last": replace(GAP.last, sequence=-1)},
    ],
)
def test_gap_breaking_the_decoder_rules_is_refused(engine: Engine, changes: dict) -> None:
    with pytest.raises(IntegrityError, match="CHECK"):
        store(engine, GapRow.from_record(replace(GAP, **changes)))


# A made-up service caller's read (S-079).
AUDIT = {
    "at_unix_ms": 1_763_683_200_000,
    "subject": "staff-1",
    "role": "service",
    "method": "GET",
    "route": "/v1/devices/{device_id}/readings",
    "device_id": "DEV-1",
    "query": "{}",
    "status": 200,
}


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_entries SET status = 404", "DELETE FROM audit_entries"]
)
def test_audit_entry_is_never_changed_or_deleted(engine: Engine, statement: str) -> None:
    store(engine, AuditRow(**AUDIT))

    with pytest.raises(DBAPIError, match="audit_entries is append-only"), engine.begin() as db:
        db.execute(text(statement))

    with Session(engine) as session:
        assert session.scalars(select(AuditRow.status)).all() == [200]


@pytest.mark.parametrize(
    "changes",
    [{"role": "auditor"}, {"status": 99}, {"status": 600}, {"subject": ""}, {"at_unix_ms": -1}],
)
def test_audit_entry_breaking_the_table_rules_is_refused(engine: Engine, changes: dict) -> None:
    with pytest.raises(IntegrityError):
        store(engine, AuditRow(**(AUDIT | changes)))
