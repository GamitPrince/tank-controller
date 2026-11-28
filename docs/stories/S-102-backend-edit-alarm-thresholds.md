# S-102: Edit a tank's alarm thresholds in the backend

- Story ID: S-102 (issue #206).
- Epic: E4, the backend half of P1-18 ("threshold alarms with audit trail"). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency.
- Part 2 of 3 of "editing level configurations and alarm thresholds with audit", stacked on S-101 (the change log, issue #205). The design and its `[Confirm]` answers are S-101's open questions 1 to 6; this spec repeats only what this story adds. Uses S-087 (the thresholds table), S-088 (`Threshold`'s rules), S-089 and S-090 (judging a scan at its own time), S-078 and S-091 (scoping, `tank_visible`) and S-080 (the service audit).

## Goal
Let a customer's admin, or our service staff, set one advisory alarm threshold on a tank, with the change kept as history and recorded in S-101's change log, so the thresholds no longer need a hand-written database row.

## Phase check
Phase 1. One `PUT` route that writes cloud settings and the change log, nothing else. These thresholds drive advisory cloud alarms for people (S-088); **they are never sent to a device** and never touch trips, interlocks or the hardwired safety chain (AGENTS.md section 1). Plant data stays read-only. No AWS resource or paid service.

## Decisions already made
- **S-101 `[Confirm]` 1 to 5:** admin (own customer) and service may edit; a change closes the row in force at the server's second and opens the next; S-087's rules plus valid range and low below high; no re-judging; one `config_changes` row in the same transaction.
- **S-087:** one open row per tank, measure, signal, direction and class; numbers in the stored unit (µA, centi-°C, hundredths of a percent).
- **S-090:** each scan is judged against `thresholds_at` its own time, so a replayed scan from before a change keeps the old limit.

## Files to create or change
- `backend/tankapi/settings_edit.py` (new): what S-102 and S-103 share: the editing roles, the tank check, the server clock, the 409 and 422 answers, and `record_change`.
- `backend/tankapi/threshold_edit.py` (new): `PUT /v1/tanks/{tank_id}/alarm-thresholds`.
- `backend/tankapi/main.py`: mounts the router.
- `backend/tests/test_threshold_edit.py` (new); `backend/tests/test_health.py` (the OpenAPI paths).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI document gains one `PUT` path. `interfaces/` is unchanged; nothing reaches a device.

## Acceptance criteria
- `PUT /v1/tanks/{tank_id}/alarm-thresholds` with `{"measure", "signal_id", "direction", "alarm_class", "limit", "deadband"}` answers `200` with those fields plus `id` (the new row), `valid_from` (the server's Unix second) and `replaced` (the closed row's ID, or null when the alarm is new).
- The open row of the same tank, measure, signal, direction and class gets `valid_to_unix_s` = that second; the new row holds from it. No row is deleted or rewritten otherwise.
- One `config_changes` row, kind `alarm_threshold`, with the caller's `sub` and role, the server time in milliseconds, the tank, and the closed and new rows' IDs and values as JSON (the rule and `valid_from`); committed with the change, or neither is kept.
- Admin of the tank's customer and service may edit; operator and maintenance get `403 {"detail": "not allowed"}`. Another customer's tank and an unknown tank answer `404 {"detail": "not found"}`. Service's requests, refused ones included, are in `audit_entries` with the tank ID (S-080). No token is `401`.
- `422` and nothing written for: a signal that takes no threshold (a digital contact), level % on a signal other than the radar or outside 0 to 100 %, a negative deadband, a signal limit outside its valid range (4,000 to 20,000 µA; 0 to 20,000 centi-°C) or a deadband wider than that range, a low limit not below the high in force of the same measure, signal and class (and the reverse), an unknown measure, direction or class, a limit that is not a whole number, an unknown or a missing field.
- A second change to the same alarm in the same server second is `409` and keeps the first; so is a clash with a stored row starting at that second.
- A scan from before the change, arriving after it, is judged by the old threshold; a later scan by the new one, and the alarm's state carries over.

## Test plan
pytest on SQLite, and on the local PostgreSQL when `TANKAPI_TEST_DATABASE_URL` is set (S-098), locally on Windows and in GitHub CI (`backend` job, SQLite only, 80% gate). The server clock is fixed in the tests. Cases: an admin's replacement with the closed row, new row and change log; a new alarm with no before; an old and a new scan ingested after a change; service on another customer's tank, audited; operator and maintenance refused; another customer's and an unknown tank; each validation failure; the valid range's ends accepted; a high above the low in force; a second change in one second; a clash with a stored row; no token; the OpenAPI paths.

## Out of scope
Removing a threshold (the change log allows it: a later story); reading the change log; editing several thresholds at once; editing the level configuration (S-103); the dashboard screen; notifications; the S3 Object Lock copy; anything that reaches a device.

## Open questions
1. `[Confirm]` A service change is committed before S-080 writes the request's audit entry; if that write fails the caller gets 503 although the change is kept. The change is still in `config_changes` with `service` as its role, so it is never unrecorded. Recommendation: keep it; joining the two writes needs S-080's middleware changed, a separate story.
2. `[Confirm]` Low below high is checked within one class only (a critical low may sit above a warning high). Recommendation: keep it; classes are independent alarms.
3. `[Confirm]` A signal's limit must lie within its valid range, so an over-range limit (above 20 mA) is refused even though S-088 judges an over-range reading as measured. Recommendation: keep it until a site asks for one.

## PR checklist notes
Title `feat(dashboard): edit a tank's alarm thresholds (S-102)`; `Closes #206`. A draft, stacked on S-101's PR, until S-101 merges; then `develop` is merged in (no rebase, no force-push) before review.
