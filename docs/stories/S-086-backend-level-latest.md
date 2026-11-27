# S-086: Serve level % and volume from stored radar readings

- Story ID: S-086 (issue #174).
- Epic: cloud, the cloud half of P1-04, part 2 of 2. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched; no new dependency. Chosen by the tech lead on 27 Nov 2026. Builds on S-085 (issue #173), which stores the configuration, and on S-082, S-083 and S-084.

## Goal
Give a live view the tank's level % and volume, computed from the device's newest radar reading with the configuration in force when it was taken, and say plainly when there is no figure and why.

## Phase check
Phase 1, read-only for plant data. One more field on an existing GET endpoint; nothing is sent to a device, nothing is stored except the existing service audit row, and computed figures are never stored as if measured. No AI or analytics. No AWS resource or account (ADR-0007's three gates still hold). No mass, and pressure level (signal 1002) is not an input.

## Decisions already made
- **ADR-0004 decision 10 and amendment 1:** level % and volume are computed in the backend; the controller is send-only. **ADR-0007 decision 9:** every result names its calculation version.
- **S-082:** `compute_level` and its statuses `ok`, `fault`, `out_of_range`, `stale`; only `ok` carries figures; nothing is substituted, clamped or extrapolated. **S-083:** a reading's liveness against the server clock.
- **S-084:** `GET /v1/devices/{device_id}/latest`, its per-customer scoping (now, and only scans from the current stretch of ownership) and the service audit by the `/v1` router (S-080). **S-074:** a reading belongs to the tank the device was on at its scan's `t`.
- **S-085:** each tank's level configuration, dated from and to, with the calculation version it is used with.

## Files to create or change
- `backend/tankapi/level_config.py` (new, split from S-085 for size): `level_config_at`, `LevelConfig`, `LevelConfigError`.
- `backend/tankapi/tank_level.py` (new): `tank_level`, `TankLevel`, `LevelState`.
- `backend/tankapi/latest.py`: the `level` field.
- `backend/tankapi/db.py` (docstring only), `backend/tests/test_level_config.py`, `backend/tests/test_latest.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI document gains `Latest.level`, `TankLevel` and the `LevelState` enum. `interfaces/` is unchanged.

## Acceptance criteria
- `level_config_at(session, tank_id, unix_time_s)` returns the configuration in force at that second, or `None`. Two in force at once raise `LevelConfigError`, and so does a stored table that `StrappingTable` refuses (fewer than two points, or one above the full height). A time that is not whole seconds raises `TypeError`.
- `/latest` returns `level` `[Confirm]` 1, computed on read from the newest radar reading (signal 1001) among the values it returns. It carries that reading's `t`, quality, age and liveness, the table version used, the calculation version, and `level_mm`, `level_percent` and `volume_l`.
- Figures come only with `status` `ok`: a live, good, in-range reading on a tank with a configuration for this calculation version. Otherwise all three are null and `status` says why: `no_reading` (no radar reading shown), `unconfigured` (the device was on no tank at `t`, the tank had no configuration then, or it was for another calculation version `[Confirm]` 2), `stale` or `time_unknown` (the reading's liveness), `fault` or `out_of_range` (S-082). A missing configuration is reported before liveness `[Confirm]` 4.
- The tank is the one the device was on at the reading's `t`, and the configuration the one in force then: a device moved to another tank keeps its old tank's figures for an old reading. A customer still sees only what S-084 shows them. Overlapping assignments or configurations, or a broken stored table, give `500 {"detail": "server error"}` and a log line, never a guess `[Confirm]` 3.
- GET only; the service audit is unchanged.

## Test plan
pytest on a fixed clock, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Helper: the configuration and its figures at and between strapping points; the configuration in force on each side of a change; none, and an unknown tank; overlap; a one-point table and a point above the full height; a non-integer time. Endpoint: the full `ok` result; fault, unconfigured, out-of-range (by quality, by current, above the table), stale (by clock and by quality) and time-unknown readings; no configuration, another calculation version, a reading from before the claim; no radar reading; a reading on each side of a configuration change; a moved device, with the old customer refused and the new one seeing no reading from before their claim; overlapping configurations; the OpenAPI field, description and enum. The service audit of this route is S-084's test, unchanged. Every tank and table is made up.

## Out of scope
An admin endpoint or screen to enter or change a configuration, with its audit entry; importing tables; storing computed results; level on the trend query (`/readings`); the `interfaces/` schemas; the pressure-level comparison (Phase 2); mass and density; alarms on level (P1-18); the dashboard (P1-21); the TimescaleDB container.

## Open questions
1. `[Confirm]` The level is a field on S-084's `/latest`, not a per-tank endpoint: it reuses that endpoint's scoping, audit and liveness and adds no route. A per-tank view can follow when the dashboard asks for one.
2. `[Confirm]` A configuration stored for another calculation version counts as none (`unconfigured`), rather than being computed with the code's version, so a figure always matches the version its table was checked with.
3. `[Confirm]` A broken or overlapping configuration refuses the whole request with 500, like S-078's overlapping assignments, rather than hiding it behind `unconfigured`.
4. `[Confirm]` `unconfigured` is reported before `stale`, `time_unknown`, `fault` and `out_of_range`, so a tank with no configuration always says so.
