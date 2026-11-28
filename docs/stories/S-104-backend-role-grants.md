# S-104: Grant the restricted backend role on every table

- Story ID: S-104 (issue #211).
- Epic: E4 (P1-20). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched. No migration, no new dependency.

## Goal
The backend's database role `tankapi_backend` holds exactly the privileges the backend's code needs on every table, and nothing else, so one item AGENTS.md lists as blocking any deployment is closed. S-098 limited the role on `audit_entries` only; S-100 to S-103 added `reading_samples`, `reading_minutes` and `config_changes` and the first UPDATEs, and the role had no rights on any of them.

## Phase check
Phase 1, read-only for plant data. A SQL grant script, tests and documentation only: no endpoint changes, nothing is sent to a device, no dashboard UI. Local only: the PostgreSQL 18.6 with TimescaleDB 2.30.0 on the development machine, no cloud account, no AWS, no Docker and no paid service (ADR-0007's three gates still hold). No login or password is created; every name in the tests is made up.

## Decisions already made
- **ADR-0008 decision 4, S-079, S-090, S-093, S-101:** `audit_entries`, `alarm_events`, `alarm_acknowledgements` and `config_changes` are append-only by triggers; the backend adds and reads them and never edits them.
- **S-098 [Confirm] 3:** the role is NOLOGIN, made once by the administrator, granted to the login the backend connects as; the grants are a documented SQL script run by the table owner.
- **S-100:** `reading_samples` is a TimescaleDB hypertable with a 90-day retention policy, summarised in the continuous aggregate `reading_minutes`. The policies run as the owner, not as the role.
- **S-102, S-103:** a settings change closes the row in force by setting `valid_to_unix_s`, then inserts the next.

## What the backend runs, table by table
Read from `backend/tankapi/` (every `select`, `session.add`, and the two attribute changes).

| Table | What the code does | Grant |
|---|---|---|
| `customers`, `plants`, `tanks`, `devices`, `device_assignments` | SELECT, to scope every request and find a device's tank (`ownership.py`, `auth`-checked routes, `alarm_events.py`) | SELECT |
| `scan_records`, `readings`, `gap_records` | INSERT at ingest, SELECT for duplicates and every read (`store.py`, `readings.py`, `latest.py`) | SELECT, INSERT |
| `reading_samples` (hypertable) | INSERT at ingest with its scan (`store.py`); not read yet | SELECT, INSERT (reaches the chunks) |
| `reading_minutes` (continuous aggregate) | nothing yet | none |
| `alarm_thresholds`, `level_configurations` | SELECT; INSERT the next row; UPDATE `valid_to_unix_s` of the row in force (`threshold_edit.py`, `level_config_edit.py`) | SELECT, INSERT, UPDATE (`valid_to_unix_s`) only |
| `strapping_points` | SELECT; INSERT with a new configuration | SELECT, INSERT |
| `alarm_events`, `alarm_acknowledgements`, `config_changes`, `audit_entries` | INSERT and SELECT; append-only by triggers | SELECT, INSERT |
| `alembic_version` | nothing (migrations run as the owner) | none |
| `<table>_id_seq` of every table above that takes an INSERT and has a generated id | `nextval` on INSERT | USAGE |

Never granted on any table: DELETE, TRUNCATE, REFERENCES, TRIGGER. Foreign keys are checked with the owner's rights, so REFERENCES is not needed. The role owns nothing, so it can run no DDL and cannot drop a trigger.

## Files to create or change
- `backend/sql/backend-role-grants.sql`: revoke everything on every table and sequence in `public`, then grant the table above.
- `backend/tests/test_backend_role.py` (new): the decisions as `EXPECTED`, the guard, the catalogue check, the refusals and the backend's own code run as the role.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`, AGENTS.md (the "Blocking any deployment" line).

## Interfaces touched
`interfaces/` is not changed. No endpoint, no OpenAPI change, no migration.

## Acceptance criteria
- After the script, on PostgreSQL, the role's table and column privileges in `public` equal `EXPECTED` exactly, its sequence USAGE equals the decided list, it owns no relation, and a second run of the script leaves the same rights.
- As `SET ROLE tankapi_backend`: UPDATE and DELETE are refused on every append-only table; UPDATE of any other column of `alarm_thresholds`, DELETE and TRUNCATE elsewhere, INSERT into the ownership tables, any read of `alembic_version` and `reading_minutes`, and CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP TRIGGER and DROP TABLE are all refused.
- The backend's own code, connected as the role, ingests a message that raises an alarm (a hypertable chunk included), acknowledges it, reads the alarm history, latest values and readings, and edits a threshold (as service, so audited) and a level configuration, all successfully.
- A guard test that runs everywhere, SQLite in CI included, fails when a model's table has no entry in `EXPECTED`, or when a granted table is missing from the script.
- With `TANKAPI_TEST_DATABASE_URL` unset, `PYTHON=python bash scripts/ci/run-component.sh backend` passes at 80% or more.

## Test plan
pytest locally on Windows (Git Bash), twice: once without the variable, once with `TANKAPI_TEST_DATABASE_URL=postgresql+psycopg://tankai_dev@localhost:5432/postgres` (password from `pgpass.conf`, not read by the agent). Both results in the PR. GitHub CI runs the first form. No bench test.

## Out of scope
The backend's deployment login and its password; a Postgres service in GitHub CI; an endpoint that reads `reading_minutes` (its story grants SELECT on it); the claim flow (its story grants INSERT on the ownership tables); trimming `readings` after 90 days (its story would grant DELETE there and only there); the S3 audit copy; Cognito; Docker.

## Open questions [Confirm]
1. **Keep the grants a hand-run SQL script, not a migration** (recommended, taken; confirmed by the tech lead, 28 Nov 2026). The role name and its existence belong to each deployment and to the administrator; a migration would tie every database, SQLite included, to it. The script is idempotent and is rerun after every migration; the deployment story runs it from the pipeline. No password either way.
2. **No default privileges for future tables** (recommended, taken; confirmed by the tech lead, 28 Nov 2026). `ALTER DEFAULT PRIVILEGES` would hand a new table's rights to the role before anyone decided them, which is the gap this story closes. Each new table gets an explicit line in the script.
3. **A guard test that fails when a new table has no grant decision** (recommended, taken; confirmed by the tech lead, 28 Nov 2026). It runs in CI on SQLite against the models, and on Postgres against the whole catalogue, so a table made only on Postgres (`reading_minutes`) is covered too.
4. **`reading_minutes` gets no grant yet** (recommended, taken; confirmed by the tech lead, 28 Nov 2026): no code reads it; the story that adds its endpoint grants SELECT.

## PR checklist notes
Title `feat(dashboard): grant the restricted backend role on every table (S-104)`, branch `feature/S-104-backend-role-grants`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. No migration, no dependency.
