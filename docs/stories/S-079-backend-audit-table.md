# S-079: Add the append-only audit table

- Story ID: S-079 (issue #161).
- Epic: E4 (P1-20). Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched. One new migration, no new dependency. Split from S-080 (#162) for PR size; S-080 writes the entries and merges after this.

## Goal
The database holds an audit table that the backend can add rows to but never edit or delete (ADR-0008 decision 4), ready for S-080 to record every service-staff request in it.

## Phase check
Phase 1, read-only for plant data. A table and its migration only: nothing writes or reads it yet, no endpoint changes and no device is contacted. No AWS resource and no account (ADR-0007's three gates still hold). Every name in the tests is made up.

## Decisions already made
- **ADR-0008 decision 4:** the audit trail is an append-only table the backend can add to but not edit or delete, plus a daily write-once S3 copy (Object Lock). The table is part of ADR-0007's "nothing deleted" rule.
- **S-068:** migrations are frozen snapshots valid in SQLite and Postgres; the models must match them.

## Files to create or change
- `backend/migrations/versions/0004_audit_entries.py` (new), `backend/tankapi/db.py` (`AuditRow`).
- `backend/tests/test_db.py`, `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
`interfaces/` is not changed. No endpoint and no OpenAPI change.

## Acceptance criteria
- Table `audit_entries`: `id`, `at_unix_ms`, `subject` (the token's `sub`, up to 128 characters), `role` (one of the four ADR-0008 roles), `method`, `route` (template), `device_id` (nullable, up to 64 characters), `query` (JSON text of the parameters that select data) and `status` (100 to 599). No column for a token, a header or a reading.
- UPDATE and DELETE on it are refused by the database, not only by Python ([Confirm] 1).
- The migration upgrades and downgrades cleanly, and the model matches it.

## Test plan
pytest on SQLite files migrated by Alembic, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI: an entry is stored, UPDATE and DELETE are each refused with "audit_entries is append-only" and leave it unchanged; an unknown role, a status of 99 or 600, an empty subject and a negative time are refused; the migration upgrades and downgrades twice; the models match it; the Postgres SQL (the function, the row and TRUNCATE triggers, and the function dropped on downgrade) renders offline. No bench test: nothing touches hardware.

## Out of scope
Writing entries (S-080); the daily S3 Object Lock copy; any audit read endpoint; other ADR-0008 events and their before and after values; the hash chain (Phase 2); retention; the database roles and grants; indexes for audit queries (with the read story).

## Open questions [Confirm]
1. **Append-only by triggers** (recommended, taken): SQLite `RAISE(ABORT)` before UPDATE and before DELETE; Postgres one PL/pgSQL function raising an exception, run before UPDATE or DELETE on each row and before TRUNCATE. **The Postgres form is untested** until the TimescaleDB container story; the tests only render it. An owner of the table can still drop a trigger or the table, so production also needs a backend database role with INSERT and SELECT only, which does not own the table (the deployment story, ADR-0008's open item on database permissions).
2. **Downgrade drops the table**, and so the trail: never run it on a database whose trail matters. A later SQLite batch migration that rebuilds the table must create its triggers again.
3. **Time as integer milliseconds** (`at_unix_ms`, recommended, taken), like the other tables' integer Unix times, with the row ID giving the order of entries in the same millisecond.

## PR checklist notes
Title `feat(dashboard): add the append-only audit table (S-079)`, branch `feature/S-079-backend-audit-table`, `Closes #161`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. One migration (0004), no new dependency.
