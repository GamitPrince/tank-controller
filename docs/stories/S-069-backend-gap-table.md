# S-069: Add the gap-record table to the backend database

- Story ID: S-069 (issue #141).
- Epic: E4 (groundwork for P1-17). Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend database can hold every gap record the decoder returns, so a later ingest story can store the holes in a device's data as well as the scans, and nothing downstream mistakes a hole for "nothing happened".

## Phase check
Phase 1, read-only. One table and one migration: no record is written by the app, no broker, no cloud account and no AWS resource (ADR-0007's three gates still hold). Tests run on a local SQLite file.

## Decisions already made
- **S-040:** the gap record: `lost` scans, from the `first` mark to the `last`, both included, were measured but dropped; the marks may come from different boots; the cloud must not interpolate across a gap.
- **S-067:** `decode_message` gives `GapRecord` with two `LostScan` marks and refuses `lost` below 1 or `t` without `tk`.
- **S-068:** split this table out for PR size; the schema conventions (named constraints, frozen-snapshot migrations, check constraints that repeat the decoder's rules, SQLite tests, Postgres-compatible DDL).

## Files to create or change
- `backend/tankapi/db.py`: `GapRow`, with `from_record` / `to_record`.
- `backend/migrations/versions/0002_gap_records.py` (revises `0001`).
- `backend/tests/test_db.py`, `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None changed. `interfaces/records.cddl` is not read.

## Acceptance criteria
- `gap_records` keeps the device ID, `lost`, and for both `first` and `last` the boot ID, sequence, uptime, time-known flag and optional Unix time.
- Check constraints: `lost` at least 1; each mark's `unix_time_s` present exactly when its `time_known` is true; boot IDs 16 bytes; device ID not empty; counters not negative.
- `alembic upgrade head` and `downgrade base` run cleanly with both revisions; the models match the migrated schema; the Postgres SQL renders offline.
- A gap whose marks come from different boots round-trips unchanged.

## Test plan
pytest, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files migrated by Alembic. No bench test: nothing touches hardware.

## Out of scope
De-duplicating gap records, writing them to the database, ingest, the TimescaleDB container and hypertables, and showing gaps on the dashboard. Everything else listed out of scope in S-068.

## Open questions [Confirm]
1. **Both marks as columns of one row** (recommended, taken). A gap always has exactly two marks, so a separate mark table would add a join and nothing else.
2. **No unique key yet.** Two gap records' ranges may overlap (S-040), and whether a redelivered gap can be told apart from a different gap with the same marks is for the de-duplication story to decide. Until then a redelivered gap would be stored twice.
3. **No link to `scan_records`.** A gap's marks name scans that never arrived, so there is no row to point at; a query places a gap on the timeline by device, boot ID, sequence and time.

## PR checklist notes
Title `feat(dashboard): add the gap-record table to the backend database (S-069)`, branch `feature/S-069-backend-gap-table`, `Closes #141`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
