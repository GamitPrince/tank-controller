# S-088: Judge a value against an alarm threshold in the backend

- Story ID: S-088 (issue #178).
- Epic: E4, the backend half of P1-18, part 2 of 5. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency. Chosen by the tech lead on 27 Nov 2026. Stacked on S-087 (the thresholds); uses S-083 (liveness) and S-086 (level %).

## Goal
Decide, for one value and one threshold, whether the value is normal, high, low or cannot be evaluated, as a pure function, so S-089 can record raised and cleared alarms from stored readings without its own rules.

## Phase check
Phase 1, read-only for plant data. A pure module: no table, no endpoint, no I/O. **These are advisory alarms for people, never actions:** nothing here, or anywhere in the backend, writes to a device or to the hardwired safety chain (AGENTS.md section 1), and a test checks that no backend module imports an MQTT or AWS client. The device's own alarm and trip contacts take no threshold. No analytics, trend or predictive alarm (P1-18).

## Decisions already made
- **P1-18:** a value whose quality is bad or whose age is past the staleness limit must not raise an alarm shown as a live plant condition; no alarm writes to any device.
- **AGENTS.md section 7:** failed sensors are flagged and excluded, never silently replaced; stale data is never shown as live.
- **S-017:** an out-of-range value is sent as measured, not clamped.
- **S-083:** a reading is `live`, `stale` or `time-unknown`. **S-086:** only an `ok` level carries figures.
- **S-087:** a threshold is one limit with a deadband, in the measure's stored unit; level % in hundredths of a percent.

## Files to create or change
- `backend/tankapi/alarm_rules.py` (new): `Threshold`, `Sample`, `reading_sample`, `level_sample`, `evaluate`, the measure, direction, class, state and reason names.
- `backend/tests/test_alarm_rules.py` (new).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged.

## Acceptance criteria
- `Threshold` refuses what migration 0006 refuses: a limit or deadband that is not a whole number, a negative deadband, a signal other than the eight analogue measurements (checked against `interfaces/signals-v1.yaml` by a test), and a level % threshold off the radar or outside 0 to 100 %.
- `evaluate(threshold, sample, active)`: a high threshold is reached at `value >= limit` and, once raised (`active`), stays reached while `value >= limit - deadband`; it clears below that. A low threshold is the mirror image. A value hovering at the limit raises once and clears once.
- A fault, unconfigured or stale-quality reading, a reading S-083 judges `stale` or `time-unknown`, no reading, or a level S-086 gives without figures gives `cannot_evaluate` with the reason, whether or not the alarm is raised: it never raises, never clears and is never reported as normal.
- An out-of-range raw reading is judged as measured `[Confirm]` 1. A level threshold uses S-086's level, so an out-of-range radar gives `cannot_evaluate` for level %.
- A sample of another measure or signal than the threshold's is refused, so a level limit is never applied to microamps.

## Test plan
pytest with made-up values and a fixed clock, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: just under, at and just over each limit, high and low; the deadband's clearing point and one unit past it; no deadband; a hovering value; fault, unconfigured, stale-quality, stale, untimed and missing readings, raised and not; out-of-range readings; level % in hundredths with every S-086 status, and through `tank_level` on a stored configuration (85 % raised, 84.9 % normal, stale, out of range); every refusal; the signal list check; no MQTT or AWS client imported.

## Out of scope
Reading the thresholds in force at a time and recording raised and cleared alarms from stored readings, with the scan time (S-089); the read endpoint (S-090); acknowledgement (S-091); an on-delay; notifications; the dashboard; alarms on staleness itself; rate-of-change, predictive or Phase 2 alarms; anything that commands a device.

## Open questions
1. `[Confirm]` An out-of-range reading is judged as measured (S-017). Level % gives no figure out of range (S-082), so an overfilled tank's radar past 20 mA raises only a raw threshold on signal 1001; the pilot tank should have one.
2. `[Confirm]` The liveness is the caller's: S-089 decides how a backlog replayed after an outage is judged, since S-083 against the server clock would call every replayed reading stale.
3. `[Confirm]` A reading at exactly the limit is reached (`>=`, `<=`), and one exactly at the clearing point stays raised.
