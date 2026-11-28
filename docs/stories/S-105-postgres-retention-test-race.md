# S-105: Fix the retention race in the Postgres tests

- Story ID: S-105 (issue #213).
- Epic: E4 (P1-17). Points: 1. Priority: Should. Component: backend (`backend/`), tests only. Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched. No migration, no production code, no new dependency.

## Goal
The opt-in PostgreSQL tests give the same result on every run. The fixed test scans are dated November 2025, more than 90 days ago, so S-100's retention policy may drop their `reading_samples` chunk in the middle of a test: S-104 saw a count come back 0 in one of four runs and worked around it in its own test. Every Postgres test that stores records is exposed, not only S-100's and S-104's.

## Phase check
Phase 1, read-only. Test fixtures and documentation only: no endpoint, no migration, nothing sent to a device. Local only: the PostgreSQL 18.6 with TimescaleDB 2.30.0 on the development machine; its server settings are not changed. SQLite and GitHub CI are unaffected (the Postgres runs are skipped there).

## Decisions already made
- **S-100 [Confirm] 4:** a 90-day retention policy on `reading_samples` and a one-minute refresh policy on `reading_minutes`, fixed in migration 0009. They stay exactly as they are.
- **S-098:** each Postgres test gets a throwaway `tankai_test` database, migrated by the `engine` fixture in `backend/tests/conftest.py`.
- **S-100's tests** already pause both policies in a fixture local to `test_reading_samples.py` and run the jobs themselves; the other test files do not.

## Files to create or change
- `backend/tests/conftest.py`: the `engine` fixture pauses the two TimescaleDB policies of the throwaway database and waits until no policy run is in flight, on every Postgres test that uses it.
- `backend/tests/test_reading_samples.py`: its local fixture is removed (now in `conftest.py`); a test that the fixture leaves the policies paused but in place, and a test that an explicit retention run drops only the chunk older than 90 days.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None.

## Acceptance criteria
- On PostgreSQL with TimescaleDB, after the `engine` fixture both policies exist, are unscheduled, and no policy run is active; the retention policy still says 90 days.
- An explicit retention run on data 100 days and 1 day old drops the old sample only, and keeps its minute in `reading_minutes` (S-100's test, kept).
- With `TANKAPI_TEST_DATABASE_URL` unset, `PYTHON=python bash scripts/ci/run-component.sh backend` passes at 80% or more.
- With it set, the full backend run passes at least three times in a row.

## Test plan
pytest locally on Windows (Git Bash): once without the variable, then at least three times with `TANKAPI_TEST_DATABASE_URL=postgresql+psycopg://tankai_dev@localhost:5432/postgres` (password from `pgpass.conf`, not read by the agent). Results in the PR. No bench test.

## Out of scope
Any change to migration 0009, the policies or their schedule; server settings such as `timescaledb.max_background_workers`; a Postgres service in GitHub CI; S-104's count of `scan_records` (still correct, left as it is).

## Open questions [Confirm]
1. **Pause the policies in the shared test fixture** (recommended, taken). `alter_job(job_id, scheduled => false)` on the throwaway database only, so no migration and no production behaviour changes, and the tests that check the policy still see it with 90 days. Alternatives: dating the Postgres test data relative to now would touch every shared fixture (`SIMULATOR_BATCH` is a captured simulator batch) and still race on the refresh policy; running the job in one test does not stop the scheduler starting it in the others.
