"""Per-second samples, their hypertable, the per-minute aggregate and retention (S-100).

The store tests run on SQLite and, when TANKAPI_TEST_DATABASE_URL is set, on PostgreSQL.
The TimescaleDB tests need that server (TimescaleDB is trusted there, S-100 [Confirm] 6).
"""

import calendar
import time

import pytest
from conftest import POSTGRES
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from test_store import BOOT, SIMULATOR_BATCH, store

from tankapi.db import SampleRow, ScanRow
from tankapi.records import Quality, Reading, ScanRecord

ON_TIMESCALE = pytest.mark.parametrize("dialect", [POSTGRES])
DAY_S = 86_400
# A minute boundary, so every test scan below falls in one known bucket.
MINUTE = 1_763_683_200
LEVEL, SWITCH = 1001, 2001
OUR_JOBS = (
    "FROM timescaledb_information.jobs"
    " WHERE hypertable_name IN ('reading_samples', 'reading_minutes')"
)
# A policy run is a background worker on this database named after its policy.
POLICY_RUNNING = (
    "SELECT count(*) FROM pg_stat_activity"
    " WHERE datname = current_database() AND application_name LIKE '%Policy%'"
)
SETTLE_TIMEOUT_S = 30
JOB_SETTING = f"SELECT config ->> :key {OUR_JOBS} AND proc_name = :proc"
POLL_S = 0.2
MINUTES = text(
    "SELECT signal_id, samples, good_samples, worst_quality, min_value, max_value,"
    " avg_value, true_samples FROM reading_minutes WHERE device_id = 'TS-1'"
    " ORDER BY minute, signal_id"
)


@pytest.fixture
def engine(engine: Engine) -> Engine:
    """The migrated database, with TimescaleDB's two policies paused where it has them.

    The scheduler may start each policy as soon as it is created, and the fixture data is
    older than 90 days, so a retention run still in flight could drop it under a test.
    The tests run the jobs themselves, once no policy run is left.
    """
    if engine.dialect.name == POSTGRES and has_timescale(engine):
        with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as db:
            db.execute(text(f"SELECT alter_job(job_id, scheduled => false) {OUR_JOBS}"))
            deadline = time.monotonic() + SETTLE_TIMEOUT_S
            quiet_polls = 0
            # Twice quiet in a row, so a worker that was just starting is seen too.
            while quiet_polls < 2:
                assert time.monotonic() < deadline, "a TimescaleDB policy run never ended"
                quiet_polls = 0 if db.scalar(text(POLICY_RUNNING)) else quiet_polls + 1
                time.sleep(POLL_S)
    return engine


def has_timescale(engine: Engine) -> bool:
    with engine.connect() as db:
        return bool(
            db.scalar(
                text("SELECT count(*) FROM pg_extension WHERE extname = :e"), {"e": "timescaledb"}
            )
        )


def scan(sequence: int, unix_time_s: int | None, *readings: Reading) -> ScanRecord:
    return ScanRecord(
        device_id="TS-1",
        signal_list_version=1,
        boot_id=BOOT,
        sequence=sequence,
        uptime_ms=sequence * 1000,
        time_known=unix_time_s is not None,
        unix_time_s=unix_time_s,
        readings=readings,
    )


def level(quality: Quality, value: int | None) -> Reading:
    return Reading(LEVEL, quality, 0, value)


def switch(quality: Quality, value: bool | None) -> Reading:
    return Reading(SWITCH, quality, 0, value)


def samples(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(SampleRow))


def refresh_minutes(engine: Engine) -> None:
    # A continuous aggregate refreshes outside a transaction only.
    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as db:
        db.execute(text("CALL refresh_continuous_aggregate('reading_minutes', NULL, NULL)"))


@pytest.mark.postgres
def test_only_time_known_scans_get_one_sample_per_reading(engine: Engine) -> None:
    store(engine, SIMULATOR_BATCH)

    timed = [record for record in SIMULATOR_BATCH if record.time_known]
    assert timed and len(timed) < len(SIMULATOR_BATCH)
    assert samples(engine) == sum(len(record.readings) for record in timed)
    with Session(engine) as session:
        rows = session.scalars(select(SampleRow).where(SampleRow.position == 0)).all()
        # SQLite gives the time back without its zone; it is UTC either way.
        times = sorted(calendar.timegm(row.t.utctimetuple()) for row in rows)
        assert times == [r.unix_time_s for r in timed]


@pytest.mark.postgres
def test_a_duplicate_scan_adds_no_samples(engine: Engine) -> None:
    store(engine, SIMULATOR_BATCH)
    before = samples(engine)

    assert store(engine, SIMULATOR_BATCH).skipped == len(SIMULATOR_BATCH)
    assert samples(engine) == before


@ON_TIMESCALE
def test_reading_samples_is_a_hypertable_with_one_day_chunks(engine: Engine) -> None:
    with engine.connect() as db:
        dimension = db.execute(
            text(
                "SELECT column_name, time_interval FROM timescaledb_information.dimensions"
                " WHERE hypertable_name = 'reading_samples'"
            )
        ).one()
    assert dimension.column_name == "t"
    assert dimension.time_interval.days == 1


@ON_TIMESCALE
def test_retention_drops_samples_after_90_days(engine: Engine) -> None:
    with engine.connect() as db:
        drop_after = db.scalar(text(JOB_SETTING), {"proc": "policy_retention", "key": "drop_after"})
        refreshed_back = db.scalar(
            text(JOB_SETTING),
            {"proc": "policy_refresh_continuous_aggregate", "key": "start_offset"},
        )
    assert drop_after == "90 days"
    # A late backlog is summarised as long as its samples are kept.
    assert refreshed_back == "90 days"


@ON_TIMESCALE
def test_minutes_summarise_good_samples_only(engine: Engine) -> None:
    store(
        engine,
        (
            scan(0, MINUTE, level(Quality.GOOD, 10), switch(Quality.GOOD, True)),
            scan(1, MINUTE + 1, level(Quality.GOOD, 20), switch(Quality.GOOD, False)),
            scan(2, MINUTE + 2, level(Quality.STALE, 1000), switch(Quality.STALE, True)),
            scan(3, MINUTE + 3, level(Quality.OUT_OF_RANGE, 5000), switch(Quality.FAULT, None)),
            scan(4, MINUTE + 4, level(Quality.FAULT, None), switch(Quality.GOOD, True)),
            # The next minute holds only a fault; a time-unknown scan is in no minute.
            scan(5, MINUTE + 60, level(Quality.FAULT, None)),
            scan(6, None, level(Quality.GOOD, 99)),
        ),
    )
    refresh_minutes(engine)

    with engine.connect() as db:
        rows = [tuple(row) for row in db.execute(MINUTES)]
    assert rows == [
        (LEVEL, 5, 2, Quality.FAULT, 10, 20, 15, 0),
        (SWITCH, 5, 3, Quality.FAULT, None, None, None, 2),
        (LEVEL, 1, 0, Quality.FAULT, None, None, None, 0),
    ]


@ON_TIMESCALE
def test_retention_keeps_recent_samples_and_every_minute(engine: Engine) -> None:
    now = int(time.time()) // 60 * 60
    store(engine, (scan(0, now - 100 * DAY_S, level(Quality.GOOD, 7)), scan(1, now - DAY_S)))
    store(engine, (scan(2, now - DAY_S + 1, level(Quality.GOOD, 8)),))
    refresh_minutes(engine)

    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as db:
        job = db.scalar(
            text(
                "SELECT job_id FROM timescaledb_information.jobs"
                " WHERE proc_name = 'policy_retention' AND hypertable_name = 'reading_samples'"
            )
        )
        db.execute(text("CALL run_job(:job)"), {"job": job})
        kept = db.scalars(text("SELECT value_int FROM reading_samples")).all()
        minutes = db.scalars(text("SELECT max_value FROM reading_minutes ORDER BY minute")).all()
    assert kept == [8]
    assert minutes == [7, 8]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ScanRow)) == 3
