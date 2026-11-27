# S-085: Store each tank's level configuration in the backend

- Story ID: S-085 (issue #173).
- Epic: cloud, the cloud half of P1-04, part 1 of 2. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; one new migration; no new dependency. Chosen by the tech lead on 27 Nov 2026. Builds on S-082 (the calculation) and S-073 (the tanks). Part 2, S-086, reads the configuration in force at a time and serves the figures.

## Goal
Store what `compute_level` (S-082) needs for each tank, with its history, so a stored radar reading can later be turned into level % and volume using the configuration that was in force when it was taken (S-086).

## Phase check
Phase 1, read-only for plant data. Two new tables; nothing is sent to a device, and no endpoint changes. No AI or analytics. No AWS resource or account (ADR-0007's three gates still hold). No mass (removed from Phase 1, 26 Nov 2026), and pressure level (signal 1002) is not an input.

## Decisions already made
- **ADR-0004 decision 10 and amendment 1:** level % and volume are computed in the backend from the tank's table; the controller is send-only.
- **ADR-0007 decision 9:** the calculation version is stored, so a figure can be reproduced from the raw archive.
- **ADR-0008 decision 3:** tank settings are the admin role's. Nothing here edits them.
- **S-082:** a configuration is a table version, the transducer range (`range_low_mm` at 4 mA, `range_high_mm` at 20 mA), the tank's full height and finished `(height_mm, volume_l)` points that rise in both height and volume. A mounting offset needs no column of its own: the range already gives the level at 4 mA.
- **S-035:** every edit makes a new version rather than overwriting the old one, and a past figure keeps the version it was computed with. A real tank's table is customer data and is never committed.

## Files to create or change
- `backend/migrations/versions/0005_level_configurations.py` (new): `level_configurations` and `strapping_points`.
- `backend/tankapi/db.py`: `LevelConfigRow`, `StrappingPointRow`.
- `backend/tests/test_level_config.py` (new), `backend/tests/test_db_migrations.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged. The `interfaces/` schemas S-035 asks for (the table and the computed record) stay a later story.

## Acceptance criteria
- A configuration belongs to one tank and holds over `[valid_from_unix_s, valid_to_unix_s)`, as a device assignment does (S-073); a tank has at most one open configuration, and two never start at the same instant or share a version `[Confirm]` 1. It stores the table version, the calculation version it is used with, the transducer range and the full height.
- The database refuses: a version or calculation version below 1; a start below 0 or an end not after the start; a range that does not rise from 0 mm or more; a full height of 0 or less; any height, volume or range that is negative, NaN or infinite; a point that does not rise in both height and volume over the point before it `[Confirm]` 2; a gap in the points' positions; and changing a point that a later point rests on.
- A configuration's numbers and its points come back as stored, the points in position order. A change closes one configuration and opens the next.
- The point count and the last point against the full height are left to the reader, which builds S-082's `StrappingTable` and so refuses both (S-086) `[Confirm]` 3.
- The migration upgrades and downgrades cleanly, its Postgres form renders offline, and the models match it.

## Test plan
pytest on SQLite, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: a configuration and its points read back in order; a change that closes one configuration and opens the next; every refusal above, each by the constraint that should refuse it; the migration up and down twice. Every tank and table is made up. No Postgres server runs these checks yet (the TimescaleDB container story).

## Out of scope
Reading the configuration in force at a time and serving the figures (S-086, split off to keep this under about 400 changed lines). An admin endpoint or screen to enter or change a configuration, with its audit entry; importing tables from files; the `interfaces/` schemas; storing computed results; the pressure-level comparison (Phase 2); mass and density; alarms on level (P1-18); the dashboard; the TimescaleDB container.

## Open questions
1. `[Confirm]` History is kept, like device assignments, rather than only the current configuration: a reading from last month is computed with last month's table, and a correction never changes a past figure silently. A correction closes the old row and opens a new one.
2. `[Confirm]` Volume must rise strictly from point to point, as S-082's `StrappingTable` requires, not merely never fall: a flat stretch would be stored but could never be used. The rule is a chain: each point repeats the point before it, and a composite foreign key holds the copy to that row, so plain check constraints do the rest on SQLite and Postgres alike.
3. `[Confirm]` The point count and the last point against the full height are checked when the configuration is read (S-086), not by the database: neither has a portable row-level form. The admin write story should refuse both before it stores anything.
