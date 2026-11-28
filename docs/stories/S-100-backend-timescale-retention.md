# S-100: TimescaleDB hypertables and retention

- Story ID: S-100 (issue #203).
- Epic: E4 (P1-20). Points: 3. Priority: Should. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched. One new migration (`0009`), no new dependency.

## Goal
The backend keeps ADR-0007 decision 5's layers in the readings database: per-second readings in a TimescaleDB hypertable that drops data older than 90 days, and per-minute summaries in a continuous aggregate that is kept forever, without ever averaging a fault, a flagged value or a gap as if it were good data.

## Phase check
Phase 1, read-only for plant data. A migration, the store's write of each new scan, tests and documentation: no endpoint changes, nothing is sent to a device, no dashboard UI. Local only: the PostgreSQL 18.6 with TimescaleDB 2.30.0 already on the development machine, no cloud account, no Tiger Cloud signup, no AWS, no Docker and no paid service (ADR-0007's three gates still hold).

## Decisions already made
- **ADR-0007 decision 4:** Tiger Cloud (managed TimescaleDB) is the production target; Timestream for InfluxDB 3 plus managed PostgreSQL is the fallback.
- **ADR-0007 decision 5:** raw archive forever, per-minute summaries (average, minimum, maximum) forever, per-second readings 90 days; the 90 days and the per-minute step are settings; the retention rule drops per-second chunks only after their aggregates exist.
- **AGENTS.md section 7:** failed sensors are flagged and excluded, never silently replaced; never show stale data as live.
- **S-040:** nothing is interpolated across a gap.
- **S-068 / S-098:** migrations are frozen snapshots valid on SQLite and Postgres; the Postgres tests are opt-in by `TANKAPI_TEST_DATABASE_URL`.

## Files to create or change
- `backend/migrations/versions/0009_reading_samples.py` (new): the `reading_samples` table everywhere; on PostgreSQL with TimescaleDB available, the extension, the hypertable, the `reading_minutes` continuous aggregate and its two policies.
- `backend/tankapi/db.py`: `SampleRow`, and `ScanRow.samples`.
- `backend/tankapi/store.py`: a new time-known scan also writes its samples.
- `backend/tests/test_reading_samples.py` (new), `backend/tests/test_db_migrations.py` (table list), `backend/tests/conftest.py` (telemetry off in the throwaway database).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`, `AGENTS.md` (the "installed but unused" line).

## Interfaces touched
`interfaces/` is not changed. No endpoint and no OpenAPI change. One migration.

## Acceptance criteria
- `alembic upgrade head` on SQLite creates `reading_samples` as a plain table, and nothing TimescaleDB-specific runs.
- On PostgreSQL with TimescaleDB available, the same upgrade creates the extension if it is missing, makes `reading_samples` a hypertable on `t` with one-day chunks, creates `reading_minutes`, a refresh policy and a 90-day retention policy; the downgrade removes them again.
- Storing a message writes one sample per reading of each new, time-known scan, in the same transaction; a duplicate scan writes no samples; a time-unknown scan writes none.
- `reading_minutes` gives, per device, signal and minute: the number of samples, the number of good samples, the worst quality, and min, max and average over good numeric samples only, plus the count of good samples that were true for a digital signal. A minute that holds only faults has no min, max or average.
- After the retention job runs, a sample older than 90 days is gone and its minute is still in `reading_minutes`; a recent sample stays.
- With `TANKAPI_TEST_DATABASE_URL` unset, `PYTHON=python bash scripts/ci/run-component.sh backend` passes at 80% or more; with it set, it passes too.

## Test plan
pytest locally on Windows (Git Bash) twice, without and with `TANKAPI_TEST_DATABASE_URL=postgresql+psycopg://tankai_dev@localhost:5432/postgres` (password from `pgpass.conf`, never read by the agent). GitHub CI runs the first form. No bench test.

## Out of scope
The raw archive (see [Confirm] 1); trimming `scan_records` and `readings` after 90 days; an endpoint that reads `reading_minutes` (the readings endpoint keeps reading `readings`); compression and tiering; per-customer retention; a Postgres service in GitHub CI; any cloud account.

## Open questions [Confirm]
All eight confirmed as recommended by the tech lead (GamitPrince) on 28 Nov 2026.
1. **Raw archive.** No table keeps the original CBOR message bytes today: `scan_records`, `readings` and `gap_records` hold the decoded fields, which are lossless for the schema but are not the original bytes. ADR-0007 decision 6 has IoT Core hand each message to the queue *and* to the raw archive, so the archive is file storage (S3), not the readings database. **Recommended, confirmed 28 Nov 2026: leave it to the ingest/queue story**, and until it exists keep `scan_records`, `readings` and `gap_records` forever, untouched by any retention. They are the local stand-in for the archive.
2. **Which table is the hypertable.** `scan_records` and `readings` cannot become hypertables without breaking things: TimescaleDB needs the time column in every primary key and unique constraint, and in the target of every foreign key. So S-070's de-duplication key `(device_id, boot_id, sequence)` would need the time column, a scan sent before and after a clock sync would no longer be found as a duplicate, and `unix_time_s` is NULL for a time-unknown scan. `readings` has no time column, and `alarm_events` (append-only, kept forever) references `scan_records.id`, so dropping old scans would break that reference. **Recommended, confirmed 28 Nov 2026: a new table `reading_samples`**, one row per reading of a time-known scan, with `t` (`timestamptz`, the scan's Unix time) as the hypertable's time column and one-day chunks (about 2 million rows per device per day, so one chunk a day stays small for a pilot). Its primary key `(scan_record_id, position, t)` contains `t`. De-duplication stays where it is: `store_message` writes samples only for scans that were new, so S-070's skipping is unchanged. The cost is that per-second data is stored twice until the archive exists and a later story trims `readings`.
3. **The per-minute aggregate.** **Recommended, confirmed 28 Nov 2026:** `reading_minutes`, grouped by device, signal and `time_bucket('1 minute', t)`, with `samples` (all samples in the minute), `good_samples`, `worst_quality` (the highest code: good 0 < stale 1 < out of range 2 < fault 3 < unconfigured 4), and `min_value`, `max_value`, `avg_value` over **good** numeric samples only, plus `true_samples` (good samples that were true) for digital signals. Stale and out-of-range values carry a number but are flagged, so they are excluded like faults. A gap is never filled: a minute with lost scans simply has `samples` below 60, and a minute with no scan has no row; the gap records stay in `gap_records`. A reader must show a minute with `good_samples` of 0 as no data, and a minute with `samples` below 60 as incomplete. Values stay in the stored scaled integers.
4. **Retention.** **Recommended, confirmed 28 Nov 2026:** `add_retention_policy('reading_samples', INTERVAL '90 days')`, and a refresh policy on `reading_minutes` every minute whose window spans the same 90 days (start offset 90 days, end offset 1 minute), so a backlog the device replays days late is still summarised before its chunk is dropped; only invalidated minutes are recomputed. Dropping raw chunks leaves the materialised minutes in place (tested). A sample that arrives already older than 90 days is dropped at the next retention run without a summary; it stays in `readings`. The hypertable gets no default index on `t` alone: the index on `(device_id, signal_id, t)` serves the reads. The 90 days and the one minute are fixed in this migration; per-customer retention, which ADR-0007 mentions, is not possible on one shared hypertable and needs its own decision.
5. **No TimescaleDB.** **Recommended, confirmed 28 Nov 2026:** `reading_samples` exists on every database as a plain table, so the store's write is tested on SQLite in CI. The hypertable, aggregate and policies run only on PostgreSQL where `pg_available_extensions` lists `timescaledb`, and are tested only by the opt-in Postgres tests. On a PostgreSQL without it, the migration logs a warning and the table stays plain (no retention), which a deployment check must catch.
6. **`CREATE EXTENSION`.** TimescaleDB 2.30.0's control file says `trusted = true`, so the owner of a database may create it without superuser rights; checked on 28 Nov 2026 with `tankai_dev` in a throwaway database. **Recommended, confirmed 28 Nov 2026: the migration runs `CREATE EXTENSION IF NOT EXISTS timescaledb`.** No step by the tech lead is needed. On Tiger Cloud the extension is already there, so the statement does nothing.
7. **Tests and the scheduler.** TimescaleDB starts a new policy at once in a background worker, so a test that stores data older than 90 days could see it dropped mid-test. `tests/test_reading_samples.py` pauses the two policies and waits until no policy worker is left, then runs the jobs itself.
8. **Telemetry.** The local server's `timescaledb.telemetry_level` is `basic`, which reports to Timescale once a database has the extension. The test fixture sets it to `off` on each throwaway `tankai_test` database. The server-wide setting is the tech lead's and is not changed here.

## PR checklist notes
Title `feat(dashboard): TimescaleDB hypertables and retention for readings (S-100)`, branch `feature/S-100-backend-timescale-retention`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
