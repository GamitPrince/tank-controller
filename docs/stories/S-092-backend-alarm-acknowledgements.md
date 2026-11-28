# S-092: Store alarm acknowledgements in the backend

- Story ID: S-092 (issue #187).
- Epic: E4, the backend half of P1-18, part 6. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; one migration (0008); no new dependency. Chosen by the tech lead on 28 Nov 2026 as "alarm acknowledgement", split in two to keep each PR near 300 lines: this table, then the endpoint (S-093). Uses S-089 (the `alarm_events` table) and S-079 (the append-only pattern).

## Goal
Give the backend somewhere to record that a person has seen a raised alarm: one append-only row per acknowledged event, with who and when, so S-093's endpoint can write it and a later story can show it.

## Phase check
Phase 1. One new cloud table; nothing writes it outside the tests yet. **An acknowledgement is a record for people only:** it never sends anything to a device, never clears, silences or mutes an alarm and never changes how S-088 judges or S-090 records one; neither reads this table. These are advisory cloud alarms, never trips or interlocks, and nothing touches the hardwired safety chain (AGENTS.md section 1). No AWS resource or paid service (ADR-0007's three gates still hold).

## Decisions already made
- **ADR-0008 decision 4, S-079, S-089:** a trail is append-only; triggers refuse UPDATE and DELETE (and TRUNCATE on Postgres); the SQLite triggers are tested and the Postgres form is rendered offline until the TimescaleDB container story.
- **S-089:** `alarm_events` is never updated, so an acknowledgement cannot be a column on it.
- **ADR-0008:** no technician role; each person has a named account, so the token's `sub` identifies who acknowledged.

## Files to create or change
- `backend/migrations/versions/0008_alarm_acknowledgements.py` (new).
- `backend/tankapi/db.py`: `AlarmAcknowledgementRow`.
- `backend/tests/test_alarm_acknowledgements.py` (new); `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None: no route, no `interfaces/` change.

## Acceptance criteria
- Table `alarm_acknowledgements`: `id`, `alarm_event_id` (foreign key to `alarm_events`, unique), `subject` (the token's `sub`, not empty), `role` (operator, maintenance or admin), `at_unix_ms` (server time, not negative) and `note` (null, or 1 to 200 characters).
- A second row for the same event, a row for an unknown event, a service role, an empty subject, an empty or over-long note and a negative time are refused by the database.
- UPDATE and DELETE are refused by triggers on SQLite; on Postgres the function and triggers (TRUNCATE too) are rendered by `alembic upgrade --sql`, and the downgrade drops the function.
- The model matches the migrated schema; upgrade and downgrade run cleanly twice.

## Test plan
pytest on SQLite, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate): rows kept with who and when; UPDATE and DELETE refused; each refused row; the migration's tables, Postgres rendering and offline downgrade.

## Out of scope
The endpoint, roles allowed and the rules for which event may be acknowledged (S-093); showing acknowledgements in S-091's history; un-acknowledging; the user's display name; the S3 Object Lock copy; the backend database role's grants (the deployment story); anything that commands a device or changes how an alarm is judged.

## Open questions
1. `[Confirm]` A new append-only table, one row per acknowledged event, never an update of `alarm_events`. The backend's database role must also lack UPDATE, DELETE and TRUNCATE on it (the deployment story, as for 0004). Recommendation: keep it.
2. `[Confirm]` The database itself refuses the `service` role, so our staff can never acknowledge for a customer by accident (S-093 recommends service be refused). Recommendation: keep it; widening it later is one migration.
3. `[Confirm]` At most one acknowledgement per event, kept by a unique key, so the first one stands and a race cannot record two. Recommendation: keep it.
4. `[Confirm]` An optional note of at most 200 characters, checked by the database too. It holds whatever a user typed, so it is never logged, and the dashboard must show it as text, not markup. Recommendation: keep it.
5. `[Confirm]` Who is the token's `sub` and role, not a name or email: a name can change and the access token carries no verified one. Mapping `sub` to a person is the Cognito story.
