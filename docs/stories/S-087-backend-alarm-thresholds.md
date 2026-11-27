# S-087: Store each tank's alarm thresholds in the backend

- Story ID: S-087 (issue #177).
- Epic: E4, the backend half of P1-18, part 1 of 5. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; one new migration; no new dependency. Chosen by the tech lead on 27 Nov 2026. Builds on S-073 (the tanks) and follows S-085's pattern. Part 2, S-088, judges a value against a threshold.

## Goal
Store each tank's advisory alarm thresholds with their history, so later stories can judge stored readings and level % against them (S-088), record raised and cleared alarms (S-089), show them (S-090) and let people acknowledge them (S-091).

## Phase check
Phase 1, read-only for plant data. One new table; no endpoint changes. **These are advisory alarms for people, never actions:** nothing is sent to a device and nothing touches the hardwired safety chain (AGENTS.md section 1). The device's own alarm and trip contacts (digital channels 1, 2 and 10 to 15) stay separate signals: the table refuses a threshold on them, so they are never relabelled as these alarms. No analytics, trend or predictive alarm (P1-18). No AWS resource, notification or paid service (ADR-0007's three gates still hold).

## Decisions already made
- **P1-18:** classes Critical, Warning and Advisory; thresholds are configurable, never hardcoded; no alarm writes to any device.
- **S-085:** configuration is kept with its history, dated from and to, so a change never alters the past silently; at most one row is open.
- **ADR-0008 decision 3:** tank settings are the admin role's. Nothing here edits them.

## Files to create or change
- `backend/migrations/versions/0006_alarm_thresholds.py` (new): `alarm_thresholds`.
- `backend/tankapi/db.py`: `AlarmThresholdRow`.
- `backend/tests/test_alarm_thresholds.py` (new), `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged.

## Acceptance criteria
- A threshold is one limit on one tank: a measure (`signal`, a stored analogue reading, or `level_percent`, S-086's level), a signal, a direction (`high` or `low`), a class (`critical`, `warning` or `advisory`), a limit and a deadband. Limit and deadband are whole numbers in the measure's stored unit: the signal's transmitted unit (`interfaces/signals-v1.yaml`: microamps, centi-degrees) or hundredths of a percent `[Confirm]` 1.
- A threshold holds over `[valid_from_unix_s, valid_to_unix_s)`; a change closes one row and opens the next. A tank has at most one open threshold per measure, signal, direction and class, so a warning and a critical high may stand on one signal together `[Confirm]` 2.
- The database refuses: an unknown tank, measure, direction or class; a signal other than the eight analogue measurements of signal list v1 (a device contact or a health signal); a level % threshold on any signal but the radar (1001), or with a limit outside 0 to 100 % or a deadband over 100 %; a negative deadband; a missing limit or deadband; a start below 0 or an end not after the start; a second open threshold of the same key, or two of the same key starting at once.
- A raw limit may be negative (a temperature below 0 °C, as measured).
- The migration upgrades and downgrades cleanly, its Postgres form renders offline, and the model matches it.

## Test plan
pytest on SQLite with made-up tanks and thresholds, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: a threshold read back as stored; a change closing one row and opening the next; several open thresholds of different classes, directions, measures and tanks; every refusal above, each by the constraint that should refuse it; the migration up and down twice and rendered for Postgres. No Postgres server runs these checks yet (the TimescaleDB container story).

## Out of scope
Judging a value against a threshold (S-088, split off for size); reading the thresholds in force at a time and recording raised and cleared alarms (S-089); the read endpoint (S-090); acknowledgement (S-091); retention of alarm history and the daily S3 Object Lock copy. An admin endpoint or screen to set thresholds: **that later write must be audited** like any configuration change (ADR-0008). Notifications; the dashboard; alarms on staleness itself or "no data from device" (ADR-0009); rate-of-change, predictive or Phase 2 alarms; anything that commands a device; the TimescaleDB container, Cognito, Docker and Terraform.

## Open questions
1. `[Confirm]` Level % thresholds are stored in hundredths of a percent, so every limit is an exact whole number in one column type, as the raw signals are.
2. `[Confirm]` One row per limit rather than a high and a low on one row, so each class and direction keeps its own deadband and history. The order between classes (critical beyond warning) is not checked; the admin write story should.
3. `[Confirm]` The deadband is required on every threshold, with no built-in default; the admin write story suggests one. There is no on-delay column; if one is wanted, it is added with S-089's rule, from configuration.
4. `[Confirm]` The eight threshold signals are a frozen list in the migration, as signal list v1 has them; a new signal list version that adds a measurement needs a migration.
5. `[Confirm]` P1-18's open questions stay open: who sets the values (per tank here), which roles acknowledge which classes (S-091), the retention of alarm history, and whether notifications are wanted.
