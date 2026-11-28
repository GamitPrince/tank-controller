# S-103: Edit a tank's level configuration in the backend

- Story ID: S-103 (issue #207).
- Epic: E4, the cloud side of P1-04 (level % and volume, ADR-0004 decision 10). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency.
- Part 3 of 3 of "editing level configurations and alarm thresholds with audit", stacked on S-102 (issue #206), which is stacked on S-101 (issue #205). The design and its `[Confirm]` answers are S-101's open questions 1 to 6. Uses S-082 (`StrappingTable`), S-085 (the tables), S-086 (`level_config_at`) and S-102's `tankapi.settings_edit`.

## Goal
Let a customer's admin, or our service staff, enter or correct a tank's transducer range, full height and strapping table, with the old configuration kept for the readings of its time and the change recorded in S-101's change log.

## Phase check
Phase 1. One `PUT` route that writes cloud settings and the change log. The configuration only turns a stored radar reading into level % and volume in the cloud (ADR-0004 decision 10); **it is never sent to a device** and never touches trips, interlocks or the hardwired safety chain (AGENTS.md section 1). No AWS resource or paid service.

## Decisions already made
- **S-101 `[Confirm]` 1 to 5**, as for S-102.
- **S-085:** one open configuration per tank; a unique version per tank; points stored chained so the database refuses one that does not rise; every number at most 1e9. **S-086:** a reading is computed with the configuration in force at its scan's time, and one for another calculation version is treated as unconfigured.

## Files to create or change
- `backend/tankapi/level_config_edit.py` (new): `PUT /v1/tanks/{tank_id}/level-configuration`.
- `backend/tankapi/main.py`: mounts the router.
- `backend/tests/test_level_config_edit.py` (new); `backend/tests/test_health.py` (the OpenAPI paths).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`, `AGENTS.md` (the open-candidates line).

## Interfaces touched
The OpenAPI document gains one `PUT` path. `interfaces/` is unchanged; nothing reaches a device.

## Acceptance criteria
- `PUT /v1/tanks/{tank_id}/level-configuration` with `{"calculation_version", "range_low_mm", "range_high_mm", "max_height_mm", "points": [{"height_mm", "volume_l"}, ...]}` answers `200` with those fields plus `id`, `version`, `valid_from` (the server's Unix second) and `replaced` (the closed configuration's ID, or null).
- The version is the tank's highest stored version plus one (1 for the first), chosen by the server; a `version` in the body is refused.
- The open configuration is closed at that second and the new one, with its points chained as S-085 stores them, holds from it. A reading from before the change is still computed with the old configuration.
- One `config_changes` row, kind `level_configuration`, with who, role, server time, tank, and the closed and new configurations' numbers, points and `valid_from` as JSON, committed with the change.
- Roles, scoping, audit and `401` as S-102: admin (own customer) and service; operator and maintenance `403`; another customer's or an unknown tank `404`; service audited.
- `422` and nothing written for: a calculation version other than the backend's (1); a range that does not rise from 0 mm; a negative number or one above 1e9, NaN or infinity; fewer than two points or more than 200 `[Confirm]` 1; points that do not rise in both height and volume; a point above the full height; an unknown, missing or non-numeric field.
- A second change in the same server second, or a clash with a stored configuration starting at that second, is `409` and keeps what was there.

## Test plan
pytest on SQLite, and on the local PostgreSQL when `TANKAPI_TEST_DATABASE_URL` is set, locally on Windows and in GitHub CI (`backend` job, SQLite only, 80% gate). The server clock is fixed. Cases: an admin's replacement with both rows and the change log; `level_config_at` before and after the change; a first configuration by service, audited; operator and maintenance refused; another customer's and an unknown tank; each validation failure; a second change in one second; a clash with a stored configuration; the OpenAPI paths.

## Out of scope
Removing a configuration; reading the change log; importing a strapping table from a file; re-computing stored figures (none are stored: level % is computed on read); the dashboard screen; anything that reaches a device.

## Open questions
1. `[Confirm]` At most 200 strapping points per configuration, so one request cannot store an unbounded table. Recommendation: keep it until a real table needs more.
2. `[Confirm]` A configuration for a later calculation version cannot be entered until the backend has that version. Recommendation: keep it; S-086 would treat it as unconfigured anyway.

## PR checklist notes
Title `feat(dashboard): edit a tank's level configuration (S-103)`; `Closes #207`. A draft, stacked on S-102's PR, until it merges; then `develop` is merged in before review.
