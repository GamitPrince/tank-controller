# S-068: Add the backend database schema and first migration

- Story ID: S-068 (issue #139).
- Epic: E4 (groundwork for P1-17). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend has database tables that hold every decoded scan record without loss, created by a versioned Alembic migration, before any storage, de-duplication or ingest story builds on them.

## Phase check
Phase 1, read-only. Tables and a migration only: no record is written by the app, no broker, no cloud account and no AWS resource (ADR-0007's three gates still hold). Tests run on a local SQLite file.

## Decisions already made
- **ADR-0007:** readings and records go to Tiger Cloud (managed TimescaleDB), so the schema stays Postgres-compatible. **AGENTS.md section 6 (26 Nov 2026):** Alembic with SQLAlchemy under `backend/migrations/`.
- **ADR-0008:** every value carries a quality flag and an age. **AGENTS.md section 7:** a failed sensor is flagged and excluded, never silently replaced.
- **S-067:** `tankapi.records.decode_message` gives `ScanRecord` and `Reading`; the tables hold exactly those fields.

## Files to create or change
- `backend/tankapi/db.py`: `ScanRow` and `ReadingRow`, with `from_record` / `to_record` mapping to and from the S-067 types.
- `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, `backend/migrations/versions/0001_records.py`.
- `backend/tests/conftest.py`, `backend/tests/test_db.py`, `backend/tests/test_db_migrations.py`.
- `backend/pyproject.toml` (`sqlalchemy>=2.1,<3`, `alembic>=1.20,<2`), `backend/requirements-dev.txt` (`sqlalchemy==2.1.9`, `alembic==1.20.1`), `backend/README.md`.
- `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None changed. `interfaces/records.cddl` is not read; the quality codes are written into the migration as a frozen snapshot.

## Acceptance criteria
- `scan_records` keeps device ID, signal-list version, boot ID, sequence, uptime, the time-known flag and the optional Unix time. `readings` keeps per reading the signal ID, quality, age and the optional value, in the order sent.
- A faulted or unconfigured reading stores no value (NULL); every other reading stores exactly one. A check constraint enforces it, so a substitute value cannot be stored.
- `unix_time_s` is present exactly when `time_known` is true; the boot ID is 16 bytes; the device ID is not empty; counters are not negative. All check constraints.
- `(device_id, boot_id, sequence)` is unique, ready for de-duplication.
- `alembic upgrade head` and `downgrade base` run cleanly, twice over; the models match the migrated schema; the migration also renders as Postgres SQL.
- The simulator batch round-trips through the tables unchanged, bools coming back as bools.

## Test plan
pytest, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. Each test migrates a fresh SQLite file with Alembic, so the tests check the migration's constraints rather than `create_all`. The Postgres DDL is checked offline (`alembic upgrade head --sql`), with no server. No bench test: nothing touches hardware.

## Out of scope
- **The gap-record table**, split out to its own story (S-069) to keep this PR near the size limit. Its design: one row per gap with `lost` (at least 1) and both lost-scan marks as columns, the same time and boot-ID checks, and nothing interpolates across it.
- The TimescaleDB container, hypertables and retention (per-second 90 days, raw archive and per-minute summaries forever): a later story against a local TimescaleDB container.
- Writing decoded records to the database, de-duplication logic, MQTT or IoT Core ingest, the managed queue, any HTTP endpoint, the customer > plant > tank > device tables and the claim flow, per-minute summaries, level % and volume, Cognito, the Docker image, Terraform and the dashboard.

## Open questions [Confirm]
1. **One row per reading, not a JSON column** (recommended, taken). Query by signal and time range (P1-17) needs a plain indexable column, the check constraint needs typed columns, and a TimescaleDB hypertable compresses narrow rows well. A JSON column would be fewer rows but would put the no-substitute rule out of the database's reach.
2. **Two value columns, `value_int` and `value_bool`** (recommended, taken). The schema allows `int / bool`, and in Python `True == 1`, so a single integer column would lose which one the device sent. The check constraint allows exactly one of them, or none for fault and unconfigured.
3. **Readings keyed by position, not signal ID** (taken). The decoder does not refuse two readings of one signal in a scan, so a `(scan, signal)` key could refuse a record the decoder accepts. Refusing duplicates belongs in the decoder and the schema together, later.
4. **SQLite for the tests** (recommended, taken). It needs no container and no install. The DDL is plain SQL valid in both, and the Postgres rendering is checked offline. The TimescaleDB story adds tests against a real server.
5. **No time column for the hypertable yet.** `unix_time_s` is NULL until the device's clock is known, so the TimescaleDB story must choose the partitioning time (for example the receive time, or the time placed afterwards from boot ID and uptime).
6. **64-bit signed columns.** The schema's `uint` has no upper limit; a value above 2^63 − 1 cannot be stored, and the database refuses it. The ingest story must report such a record rather than wrap it.

## PR checklist notes
Title `feat(dashboard): add the backend database schema and first migration (S-068)`, branch `feature/S-068-backend-db-schema`, `Closes #139`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
