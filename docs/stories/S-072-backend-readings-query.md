# S-072: Query stored readings by signal and time range

- Story ID: S-072 (issue #147).
- Epic: E4 (groundwork for P1-17 and P1-23). Points: 3. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The first versioned REST endpoint: one device's stored readings of one signal over a time range, each with its quality and age, with the gaps in that range returned as gaps. It meets P1-17's "queryable by signal and time range" criterion for what is stored today.

## Phase check
Phase 1, read-only. One `GET` endpoint reading the backend's own database: nothing is written, no device is ever answered or commanded, no cloud account and no AWS resource (ADR-0007's three gates still hold). Tests run on local SQLite files.

## Decisions already made
- **ADR-0008 decision 7:** REST with OpenAPI, versioned. The version prefix starts here (S-066 [Confirm] 3), so the path is `/v1/...`.
- **ADR-0008:** a quality flag and an age on every value; the backend checks every request (login is a later story, see [Confirm] 4).
- **AGENTS.md section 7:** a failed sensor is flagged and excluded, never replaced; stale data is never shown as live.
- **S-040:** nothing is interpolated across a gap.
- **ADR-0004 decision 11:** a scan with `tk` false has no wall-clock time.
- **S-068 to S-071:** the tables, `store_message` and `ingest_message`.

## Files to create or change
- `backend/tankapi/readings.py`: the router and `GET /v1/devices/{device_id}/readings`.
- `backend/tankapi/session.py`: the per-request session, from `TANKAPI_DATABASE_URL`.
- `backend/tankapi/main.py`: includes the router.
- `backend/tests/test_readings.py`; `backend/tests/test_health.py` (the OpenAPI test now expects both paths).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

No migration and no new dependency.

## Interfaces touched
None changed. Quality codes and scaled values are read as `interfaces/records.cddl` and `interfaces/signals-v1.yaml` define them.

## Acceptance criteria
- `GET /v1/devices/{device_id}/readings?signal=<id>&from=<t>&to=<t>`, with `from` and `to` in Unix seconds UTC, returns the readings of that signal whose scan time is in `[from, to)`, oldest first.
- Every point has `t`, `boot_id` (hex), `sequence`, `signal_list_version`, `quality` (`good`, `stale`, `out_of_range`, `fault`, `unconfigured`), `age_ms` and `value`. A fault or unconfigured reading has `value` null. An out-of-range value is returned as measured.
- Gaps of the device that overlap the range, or may overlap it because one end's time is unknown, are returned in `gaps` with `lost` and both marks. Nothing is filled in.
- Scans with no wall-clock time are not in `points` and are counted in `untimed.points`; gaps with neither time known are counted in `untimed.gaps`.
- `from >= to`, a range over 3600 s, a missing or non-integer parameter, a negative number or a device ID over 64 characters gives 422. More than 3600 matching points gives 422, asking for a narrower range. A device with no stored records gives 404.
- `POST`, `PUT`, `PATCH` and `DELETE` give 405. OpenAPI documents only `GET` paths.

## Test plan
pytest with FastAPI's `TestClient`, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files migrated by Alembic. The simulator fixture is ingested with `ingest_message`, then queried: an out-of-range reading, a faulted reading, a bool reading, scans with unknown time, gaps inside, partly unknown, fully unknown and outside the range, an empty range, eight bad parameter sets and a long device ID (422), an unknown device (404), the point limit (422), the four write methods (405) and the session's database URL. No bench test: nothing touches hardware.

## Out of scope
Cognito login and per-customer or per-tank access; the customer > plant > tank > device tables and the claim flow; the stale-data logic of P1-19 beyond returning quality and age; server-sent events and polling; per-minute summaries; CSV and PDF export; level % and volume; an index on scan time (needs a migration); the TimescaleDB container and retention; the queue consumer; the IoT Core rule; the Docker image; Terraform; the dashboard.

## Open questions [Confirm]
1. **Scaled integers, not engineering values** (recommended, taken). Values come back as stored, with the signal-list version of each scan, and the client multiplies by the signal's `scale`. The backend does not parse `signals-v1.yaml`, so it needs no YAML dependency, and a value cannot be mis-scaled under the wrong list version. Applying the scale in the backend is the alternative, once it loads the signal list.
2. **Unknown-time scans are excluded and counted** (recommended, taken). They cannot be placed in a time range without inference; they are never stamped with arrival time. Placing them by boot ID and uptime against a later timed scan of the same boot is a possible later story.
3. **Limits: one hour per request and 3600 points** (recommended, taken). One hour of one-second scans; more points (only after a clock step back) is refused rather than cut. Longer trends will read per-minute summaries (ADR-0007, P1-23).
4. **No login yet.** The endpoint is unauthenticated, runs locally only, and must not be deployed before the login and per-customer access story lands (ADR-0008: the backend checks every request).
5. **A gap with one unknown end is treated as open on that side**, so it appears in every range on that side of its known end. Honest, but it may show an old gap in later queries.
6. **An unknown signal ID on a known device returns no points**, not 404: the backend does not read the signal list yet.

## PR checklist notes
Title `feat(dashboard): query stored readings by signal and time range (S-072)`, branch `feature/S-072-backend-readings-query`, `Closes #147`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
