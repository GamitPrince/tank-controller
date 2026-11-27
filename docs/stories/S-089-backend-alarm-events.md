# S-089: Store raised and cleared alarm events in the backend

- Story ID: S-089 (issue #181).
- Epic: E4, the backend half of P1-18, part 3 of 6. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; one new migration; no new dependency. Chosen by the tech lead on 27 Nov 2026. Builds on S-087 (thresholds), S-088 (the evaluator's states and reasons) and S-079 (the append-only trigger approach). Part 4, S-090, judges stored scans and writes these rows; it was split off for size, so the read endpoint and acknowledgement move to S-091 and S-092.

## Goal
Keep a history of each advisory alarm that cannot be edited: one row per change of state, judged from one stored scan, with the threshold in force at that scan's time.

## Phase check
Phase 1, read-only for plant data. One new table and a read helper; no endpoint changes. **These are advisory alarms for people, never actions:** nothing is sent to a device and nothing touches the hardwired safety chain (AGENTS.md section 1). The device's own alarm and trip contacts (digital channels 1, 2 and 10 to 15) stay separate signals and take no threshold (S-087). No AWS resource, notification or paid service (ADR-0007's three gates still hold).

## Decisions already made
- **P1-18:** alarm history cannot be edited: an append-only table plus a daily S3 Object Lock copy (ADR-0008 decision 4). The copy is a later story.
- **S-079:** append-only means database triggers that refuse UPDATE and DELETE (and TRUNCATE on Postgres); the Postgres form is rendered, not yet run on a server.
- **S-087:** a threshold is one row with history; **S-088:** the states `normal`, `high`, `low`, `cannot_evaluate` and its reasons.
- **AGENTS.md section 5 and ADR-0004 decision 11:** a record keeps the device's scan time; an untimed scan has none.

## Files to create or change
- `backend/migrations/versions/0007_alarm_events.py` (new): `alarm_events` and its triggers.
- `backend/tankapi/db.py`: `AlarmEventRow`. `backend/tankapi/thresholds.py` (new): `thresholds_at`, `ThresholdInForce`, `ThresholdError`.
- `backend/tests/test_alarm_events.py` (new), `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`; the pointers to this story in the S-087 and S-088 specs.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged.

## Acceptance criteria
- An event row is one change of one alarm's state: the threshold row in force (its ID is the version), a copy of its limit and deadband, the scan it was judged from and that scan's `t` (never the time of arrival), the state, the reason when it is `cannot_evaluate`, the value judged in the measure's stored unit, and the reading's quality code. A clear is a new row `[Confirm]` 1.
- The database refuses: UPDATE and DELETE of any row (triggers, as S-079); an unknown state or reason; a judged state with a reason or without a value; `cannot_evaluate` without a reason or with a value; a quality outside 0 to 4; no quality unless the reason is `no_reading`; an untimed row unless it is `cannot_evaluate` for `time_unknown`; a negative time or deadband; an unknown threshold or scan; a second row for one threshold and one scan.
- `thresholds_at(session, tank_id, t)` returns the tank's thresholds in force at `t` (start included, end excluded), each with its row ID and key (tank, measure, signal, direction, class); two rows of one key in force at once raise `ThresholdError`; an untimed or fractional time is refused.
- The migration upgrades and downgrades cleanly, its Postgres form (with the triggers) renders offline, and the model matches it.

## Test plan
pytest on SQLite with made-up tanks, scans and thresholds, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: a raise, an untimed scan and a clear read back in order; UPDATE and DELETE refused; every refusal above, each by its named constraint; thresholds before, at and after a change, of another tank and starting later; an overlap refused; the migration up and down twice and rendered for Postgres, with the downgrade dropping the trigger function. No Postgres server runs these checks yet (the TimescaleDB container story).

## Out of scope
Judging scans and writing these rows (S-090); the read endpoint (S-091); acknowledgement (S-092); retention of alarm history and the S3 Object Lock copy; notifications; the dashboard; an admin endpoint for thresholds; alarms on staleness itself; Phase 2 alarms; anything that commands a device; the TimescaleDB container, Cognito, Docker and Terraform.

## Open questions
1. `[Confirm]` One row per change of state, not per reading: a value that stays high writes nothing more. The implicit state before an alarm's first row is `normal`, so a first reading that is normal writes nothing (S-090).
2. `[Confirm]` An alarm is its threshold key, not its row: a changed limit opens a new row of the same key, and the alarm keeps its state across it, judged with the new limit and deadband. Each event copies the limit and deadband, so the history holds even if a threshold row were edited in place.
3. `[Confirm]` The value is stored as a float in the measure's stored unit: whole microamps or centi-degrees for a signal, hundredths of a percent for level %. A float holds every such whole number exactly.
4. `[Confirm]` The backend's database role must lack UPDATE, DELETE and TRUNCATE on `alarm_events` and must not own it, as for `audit_entries` (the deployment story). The Postgres triggers are untested on a server until the TimescaleDB container story.
5. `[Confirm]` A threshold closed with no successor, or a device moved to another tank, leaves its alarm's last row standing; the admin write story (or S-091's view) decides how a raised alarm with no threshold in force is shown.

## PR checklist notes
Title `feat(dashboard): store raised and cleared alarm events in the backend (S-089)` (the `dashboard` scope, S-066 `[Confirm]` 1), `Closes #181`. `interfaces/` and `.github/` unchanged.
