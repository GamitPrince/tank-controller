from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tankapi.db import GapRow, ReadingRow, ScanRow
from tankapi.records import GapRecord, LostScan, Message, ScanRecord, decode_message
from tankapi.store import StoreResult, store_message

pytestmark = pytest.mark.postgres

# The S-067 fixture: five simulator scans, seq 0 to 4, time known from seq 3,
# 2001 faulted, 1001 out of range, and the digital inputs as bools.
SIMULATOR_BATCH = decode_message(
    bytes.fromhex((Path(__file__).parent / "fixtures" / "simulator-batch-cbor-hex.txt").read_text())
)
BOOT = bytes(range(16))
GAP = GapRecord(
    device_id="SIM-0001",
    lost=7,
    first=LostScan(BOOT, sequence=3, uptime_ms=3000, time_known=False, unix_time_s=None),
    last=LostScan(bytes(16), sequence=9, uptime_ms=900, time_known=True, unix_time_s=1_763_683_209),
)


def store(engine: Engine, records: tuple[Message, ...]) -> StoreResult:
    with Session(engine) as session:
        return store_message(session, records)


def stored_scans(engine: Engine) -> tuple[ScanRecord, ...]:
    with Session(engine) as session:
        rows = session.scalars(select(ScanRow).order_by(ScanRow.sequence)).all()
        return tuple(row.to_record() for row in rows)


def stored_gaps(engine: Engine) -> list[GapRecord]:
    with Session(engine) as session:
        return [row.to_record() for row in session.scalars(select(GapRow).order_by(GapRow.id))]


def count(engine: Engine, model: type) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def test_simulator_batch_is_stored_and_read_back_field_for_field(engine: Engine) -> None:
    assert store(engine, SIMULATOR_BATCH) == StoreResult(stored=5, skipped=0)

    stored = stored_scans(engine)
    assert stored == SIMULATOR_BATCH

    # True == 1 in Python, so compare the value types too: a bool must come back a bool.
    def types(batch: tuple[ScanRecord, ...]) -> list[type]:
        return [type(x.value) for record in batch for x in record.readings]

    assert types(stored) == types(SIMULATOR_BATCH)
    # The device's own time, not the arrival time: unknown until seq 3.
    assert [(s.uptime_ms, s.unix_time_s) for s in stored][2:4] == [(2000, None), (3000, 1763683203)]


def test_same_message_twice_stores_nothing_the_second_time(engine: Engine) -> None:
    store(engine, SIMULATOR_BATCH)

    assert store(engine, SIMULATOR_BATCH) == StoreResult(stored=0, skipped=5)
    assert stored_scans(engine) == SIMULATOR_BATCH
    assert count(engine, ReadingRow) == 5 * 27


def test_overlapping_batch_stores_only_the_new_scans(engine: Engine) -> None:
    store(engine, SIMULATOR_BATCH[:3])

    assert store(engine, SIMULATOR_BATCH[1:]) == StoreResult(stored=2, skipped=2)
    assert stored_scans(engine) == SIMULATOR_BATCH


def test_redelivered_scan_is_skipped_not_overwritten(engine: Engine) -> None:
    store(engine, SIMULATOR_BATCH[:1])
    changed = replace(SIMULATOR_BATCH[0], uptime_ms=99, readings=())

    assert store(engine, (changed,)) == StoreResult(stored=0, skipped=1)
    assert stored_scans(engine) == SIMULATOR_BATCH[:1]


def test_duplicate_inside_one_message_is_stored_once(engine: Engine) -> None:
    first = SIMULATOR_BATCH[0]

    assert store(engine, (first, first)) == StoreResult(stored=1, skipped=1)


def test_same_sequence_on_another_boot_or_device_is_a_new_scan(engine: Engine) -> None:
    first = SIMULATOR_BATCH[0]
    others = (replace(first, boot_id=BOOT), replace(first, device_id="SIM-0002"))

    assert store(engine, (first, *others)) == StoreResult(stored=3, skipped=0)


def test_gap_is_stored_and_a_redelivered_gap_skipped(engine: Engine) -> None:
    assert store(engine, (*SIMULATOR_BATCH[:2], GAP)) == StoreResult(stored=3, skipped=0)

    assert store(engine, (GAP,)) == StoreResult(stored=0, skipped=1)
    assert stored_gaps(engine) == [GAP]


@pytest.mark.parametrize(
    "other",
    [
        # A gap carried forward keeps its first mark but covers more (S-040).
        replace(GAP, lost=9, last=replace(GAP.last, sequence=11, uptime_ms=1100)),
        replace(GAP, first=replace(GAP.first, time_known=True, unix_time_s=1_763_683_203)),
        replace(GAP, device_id="SIM-0002"),
    ],
)
def test_gap_differing_in_any_field_is_a_new_gap(engine: Engine, other: GapRecord) -> None:
    store(engine, (GAP,))

    assert store(engine, (other,)) == StoreResult(stored=1, skipped=0)
    assert stored_gaps(engine) == [GAP, other]


def test_failure_part_way_through_writes_nothing(engine: Engine) -> None:
    # The decoder never returns this; the database refuses it (S-068 check constraint).
    refused = replace(SIMULATOR_BATCH[1], device_id="")

    with pytest.raises(IntegrityError, match="(?i)check constraint"):
        store(engine, (SIMULATOR_BATCH[0], refused, GAP, *SIMULATOR_BATCH[2:]))

    assert (count(engine, ScanRow), count(engine, ReadingRow), count(engine, GapRow)) == (0, 0, 0)
    # Rolled back cleanly: the next delivery of the message is stored in full.
    assert store(engine, SIMULATOR_BATCH) == StoreResult(stored=5, skipped=0)
