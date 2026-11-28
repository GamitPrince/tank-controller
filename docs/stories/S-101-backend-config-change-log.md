# S-101: An append-only change log for a tank's settings

- Story ID: S-101 (issue #205). S-102 is issue #206, S-103 issue #207.
- Epic: E4, the backend half of P1-18 ("threshold alarms with audit trail") and of P1-04's level configuration. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; one migration; no new dependency.
- Part 1 of 3 of the tech lead's "editing level configurations and alarm thresholds with audit" (AGENTS.md section 10, open candidates, 28 Nov 2026). The work came to well over 300 lines, so it is split into three stacked stories `[Confirm]` 6: **S-101** this table, **S-102** editing alarm thresholds, **S-103** editing the level configuration. S-102 and S-103 build on this one.

## Goal
Give the backend one place that records every change a person makes to a tank's settings: who made it, with which role, when (server time), on which tank, and the value before and after. S-102 and S-103 write it; nothing reads it yet.

## Phase check
Phase 1. One new append-only table in the cloud database. These settings are advisory alarm thresholds (S-087) and the level configuration behind the level % and volume display (S-085). **They are never sent to a device** and never touch trips, interlocks, safe states or the hardwired safety chain (AGENTS.md section 1). No AWS resource, Docker or paid service.

## Decisions already made
- **ADR-0008 decision 4:** the audit trail is an append-only table; the backend may add rows but never edit or delete them. S-079 enforces that with triggers (UPDATE, DELETE, and TRUNCATE on Postgres); S-089 and S-092 repeat the pattern.
- **ADR-0008 decision 3, S-080:** every service request is recorded in `audit_entries`, refused ones included. Customer callers are not recorded there.
- **S-085, S-087:** a configuration or a threshold holds over `[valid_from_unix_s, valid_to_unix_s)`; a change closes one row and opens the next.

## Files to create or change
- `backend/migrations/versions/0010_config_changes.py` (new): the `config_changes` table and its append-only triggers.
- `backend/tankapi/db.py`: `ConfigChangeRow`.
- `backend/tests/test_config_changes.py` (new); `backend/tests/test_db_migrations.py` (the offline Postgres render list).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None outside the database. No endpoint, nothing in `interfaces/`, nothing to a device.

## Acceptance criteria
- `config_changes` has `id`, `at_unix_ms` (server time), `subject` (the token's `sub`), `role`, `tank_id` (a foreign key to `tanks`), `kind` (`alarm_threshold` or `level_configuration`), `before_row_id` and `after_row_id` (the closed and the opened row of that kind; either may be empty) and `before` and `after` (the values as JSON text; either may be empty, never both).
- `role` is `admin` or `service` only, the roles that may edit `[Confirm]` 1. `subject` is not empty and `at_unix_ms` is not negative.
- An empty `before` goes with an empty `before_row_id`, and likewise for `after`, so a change is always one of: created, replaced, or (later) removed.
- UPDATE and DELETE are refused on SQLite and Postgres, and TRUNCATE on Postgres, by triggers, as in migration 0004.
- `ConfigChangeRow` matches the migrated schema; the Postgres SQL renders offline; upgrade and downgrade run cleanly.

## Test plan
pytest on SQLite, and on the local PostgreSQL when `TANKAPI_TEST_DATABASE_URL` is set (S-098), locally on Windows and in GitHub CI (`backend` job, SQLite only, 80% gate). Cases: a valid row of each kind stored; each check refused (role, kind, empty subject, negative time, unknown tank, neither before nor after, a value without its row ID and the reverse); UPDATE, DELETE and (Postgres) TRUNCATE refused; the migration list tests.

## Out of scope
The edit endpoints (S-102, S-103); an endpoint that reads the change log; removing a threshold; the S3 Object Lock copy of the audit trail; the restricted database role's grants on this table (the deployment story, as for S-098's `audit_entries`); the dashboard.

## Open questions
These are the design questions for all three stories; each is answered here with a recommendation and taken.
1. `[Confirm]` **Who may edit.** The customer's **admin**, for their own customer's tanks, and **service** (our staff) for any tank. Operator and maintenance keep read access only and get `403`. ADR-0008 gives admin the customer's configuration, and service commissions sites. Recommendation: keep it.
2. `[Confirm]` **History, never rewrite.** A change closes the row in force (sets its `valid_to_unix_s` to the server's time) and opens a new one from that same second. Nothing is ever deleted or overwritten, so ingest keeps judging an old or replayed scan by the threshold and configuration of the scan's own time (`thresholds_at`, `level_config_at`). The time is the server's, never the client's: no back-dating, no future-dating. A second change to the same row within the same second is refused with `409` rather than overwriting the first (the schema needs `valid_to > valid_from`).
3. `[Confirm]` **Validation.** Thresholds: S-087's rules (one of the eight analogue signals, level % only on the radar and within 0 to 100 %, deadband not negative), plus the limit within the signal's valid range in its transmitted unit (4,000 to 20,000 µA, 0 to 20,000 centi-°C), and a low limit below the high limit of the same measure, signal and class in force (and the reverse). Level configuration: S-082's `StrappingTable` (finite numbers, a range rising from 0 mm, at least two points rising in height and volume, none above the full height) and S-085's ceiling of 1e9; the calculation version is the backend's current one, and the configuration's version is the previous one plus one, chosen by the server.
4. `[Confirm]` **No re-judging.** A change does not re-judge stored scans or rewrite alarm events. The next scan, by its own time, is judged against the new threshold; the alarm's state carries over because its key (tank, measure, signal, direction, class) is unchanged. Recommendation: keep it; re-judging history would change what people were shown at the time.
5. `[Confirm]` **What is audited, and where.** Every change, by admin or service, writes one `config_changes` row in the same transaction as the change: who, role, server time, tank, kind, and the before and after values. It is its own append-only table rather than `audit_entries`, because `audit_entries` records requests (route, status, selection) and has no place for values, and S-080 deliberately records only service callers. Service's requests are still recorded in `audit_entries` by S-080, as every `/v1` request is. A change and its `config_changes` row commit together, so no change is ever unrecorded even when S-080's later write of the request fails (503).
6. `[Confirm]` **One story or several.** Three stacked stories, each near 300 lines: S-101 (this table), S-102 (thresholds), S-103 (level configuration). S-102 and S-103 are drafts until the one below merges, and `develop` is merged into each before review.

## PR checklist notes
Title `feat(dashboard): an append-only change log for a tank's settings (S-101)`; `Closes #205`. No safety path, no `interfaces/` change.
