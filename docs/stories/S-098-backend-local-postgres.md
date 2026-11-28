# S-098: Test the backend on a local PostgreSQL

- Story ID: S-098 (issue #199).
- Epic: E4 (P1-20). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched. One new test dependency (the Postgres driver), no new migration.

## Goal
The backend's migrations and database tests run against a real PostgreSQL server as well as SQLite, so two items that AGENTS.md lists as blocking any deployment are closed: S-079's append-only Postgres triggers are proven on a server, and a backend database role exists that may only INSERT and SELECT `audit_entries`.

## Phase check
Phase 1, read-only for plant data. Tests, a test fixture, a SQL grant script and documentation only: no endpoint changes, nothing is sent to a device, no dashboard UI. Local only: the PostgreSQL 18 already installed on the development machine, no cloud account, no AWS, no Docker and no paid service (ADR-0007's three gates still hold). Every name in the tests is made up.

## Decisions already made
- **ADR-0008 decision 4:** the audit trail is append-only; the backend may add to it but never edit or delete it.
- **S-068:** migrations are frozen snapshots valid in SQLite and Postgres; the models must match them.
- **S-079 [Confirm] 1:** append-only by triggers; the Postgres form was rendered only, untested on a server; production needs a backend role with INSERT and SELECT only, which does not own the table.
- **AGENTS.md section 3:** CI is not edited here; the `backend` job keeps running on SQLite alone.

## Local setup (done by hand by the tech lead, 28 Nov 2026)
The PostgreSQL 18.6 service `postgresql-x64-18` runs on port 5432, with TimescaleDB 2.30.0 installed and preloaded (not used here). As `postgres`, the tech lead created a login `tankai_dev` (CREATEDB, not superuser, not CREATEROLE), a role `tankapi_backend` (NOLOGIN, no password) granted to `tankai_dev`, and a `pgpass.conf` holding the login's password. No agent created a login, read the password or changed `pg_hba.conf`.

## Files to create or change
- `backend/tests/conftest.py`: the `postgres` marker, the `dialect` fixture and a throwaway `tankai_test` database per Postgres test.
- `backend/tests/test_postgres.py` (new): TRUNCATE refused, and the backend role's rights.
- `backend/sql/backend-role-grants.sql` (new): the grants on `audit_entries` and its sequence.
- `pytestmark = pytest.mark.postgres` in `test_db_migrations.py`, `test_db.py`, `test_store.py`, `test_ingest.py`, `test_audit.py`, `test_alarm_events.py`, `test_alarm_acknowledgements.py`, `test_alarm_recording.py`, with only the small assertion changes Postgres needs.
- `backend/requirements-dev.txt` (the driver), `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
`interfaces/` is not changed. No endpoint and no OpenAPI change. No migration.

## Acceptance criteria
- With `TANKAPI_TEST_DATABASE_URL` unset, `PYTHON=python bash scripts/ci/run-component.sh backend` passes at 80% or more, and every Postgres run is reported as skipped.
- With it set to the local server, the same command also passes, and:
  - the migrations upgrade to head and downgrade to base twice on Postgres, and the models match the migrated schema there;
  - UPDATE and DELETE on `audit_entries`, `alarm_events` and `alarm_acknowledgements` are refused by their triggers, and so is TRUNCATE, even with CASCADE (a plain TRUNCATE of `alarm_events` is already stopped by the acknowledgements' foreign key before its trigger runs);
  - after `backend-role-grants.sql`, `tankapi_backend` holds exactly SELECT and INSERT on `audit_entries`, does not own it, can add and read an entry, and is denied UPDATE, DELETE and TRUNCATE;
  - the store, ingest, audit and alarm tests named above pass on Postgres too.
- Each Postgres test makes its own `tankai_test` database and drops it afterwards; if a database of that name already exists the test fails rather than use or drop it.
- No password or credential is in the repository or in any test output.

## Test plan
pytest locally on Windows (Git Bash) twice: once without the variable, once with `TANKAPI_TEST_DATABASE_URL=postgresql+psycopg://tankai_dev@localhost:5432/postgres` (the password comes from `pgpass.conf`). Both results are recorded in the PR. GitHub CI runs the first form. No bench test: nothing touches hardware.

## Out of scope
A Postgres service in `.github/workflows/ci.yml` (a separate story, since `.github/` is not edited here); TimescaleDB, hypertables and retention (their own story); grants for the other tables and the backend's login for a deployment; the daily S3 Object Lock audit copy; Cognito; Docker.

## Open questions [Confirm]
1. **Driver: `psycopg[binary]` 3.3.9** (recommended, taken), pinned in `requirements-dev.txt` and installed only into `backend/.venv`. It is the maintained Postgres driver SQLAlchemy 2.1 supports, and the binary wheel carries its own libpq, so nothing is installed globally. It is not added to `pyproject.toml`'s runtime dependencies until a deployment story needs it.
2. **Opt-in by `TANKAPI_TEST_DATABASE_URL`** (recommended, taken): a server URL with no password in it; unset, the Postgres runs are skipped so CI stays green with no Postgres service. Only modules marked `postgres` run on both; the rest stay SQLite-only because their assertions match SQLite's error text or are not about the database.
3. **The restricted role by a documented SQL script, not a migration** (recommended, taken): `backend/sql/backend-role-grants.sql`, run by the table owner after `alembic upgrade head`. A migration would tie every database, SQLite included, to a role name the deployment has not chosen, and creating a role is a server-level act for the administrator. The role is NOLOGIN with no password, and no password is in the repository.
4. **TimescaleDB is not used** (recommended, taken): it is installed and preloaded on this machine, but hypertables and retention are their own story.
5. **One fixed database name, `tankai_test`**, created and dropped per test (recommended, taken): simple and safe on a developer machine. Tests cannot run in parallel against one server; nobody runs them in parallel today.

## PR checklist notes
Title `test(dashboard): run the backend tests on a local PostgreSQL (S-098)`, branch `feature/S-098-backend-local-postgres`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. No migration; one test dependency.
