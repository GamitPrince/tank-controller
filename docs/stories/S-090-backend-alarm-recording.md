# S-090: Record raised and cleared alarms in the backend

- Story ID: S-090 (issue #182).
- Epic: E4, the backend half of P1-18, part 4 of 6. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency. Chosen by the tech lead on 27 Nov 2026. Stacked on S-089 (the `alarm_events` table and `thresholds_at`); uses S-070 and S-071 (store and ingest), S-074 (owner at a time), S-083 (liveness), S-086 (level %) and S-088 (the evaluator).

## Goal
Judge every newly stored scan against the thresholds in force at its own time and record each change of an alarm's state, so a raised or cleared advisory alarm is in the history as it happened, even when the readings arrive late.

## Phase check
Phase 1, read-only for plant data. Ingest gains one step in its own transaction; no endpoint changes. **These are advisory alarms for people, never actions:** nothing is sent to a device and nothing touches the hardwired safety chain (AGENTS.md section 1), and S-088's test that no backend module imports an MQTT or AWS client still holds. The device's own alarm and trip contacts stay separate signals. No AWS resource, notification or paid service (ADR-0007's three gates still hold).

## Decisions already made
- **P1-18 and AGENTS.md section 7:** a bad-quality or stale value never raises an alarm shown as a live condition; failed sensors are flagged and excluded.
- **S-070:** a stored record is skipped when it arrives again. **S-071:** one message is decoded, checked and stored in one transaction.
- **S-073 `[Confirm]` 3:** an untimed scan is never placed on a tank by its arrival time.
- **S-089:** one event row per change of state, append-only, at the scan's time.

## Files to create or change
- `backend/tankapi/alarm_events.py` (new): `record_alarm_events`.
- `backend/tankapi/store.py`: `store_message` takes `then`, called in the same transaction with the new scans. `backend/tankapi/ingest.py`: passes the alarm step, and takes `clock` so tests fix the server clock.
- `backend/tests/test_alarm_recording.py` (new).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged.

## Acceptance criteria
- The alarm step runs inside the ingest transaction, on the scans that were new. A redelivered message adds no event, and if the step fails, the message's records are not stored either `[Confirm]` 1.
- Each scan is judged against the thresholds of the tank its device was on at the scan's `t`, with S-088's rule. One row is added only when an alarm's state changes, so a value that stays high adds nothing.
- A scan is judged at its own time. A reading is stale when the device marked it so or its `age` is over two update periods (S-083 with the scan's own time as the clock), never because it arrived late. A replayed backlog raises and clears alarms at the times it happened `[Confirm]` 2.
- A fault, unconfigured, stale or missing reading, an untimed scan, or a scan more than S-083's allowance ahead of the server clock gives `cannot_evaluate` with the reason. It never raises or clears an alarm: once the value can be judged again, a raised alarm inside its deadband stays raised.
- An untimed scan is judged against the thresholds of the tank its device was on at its newest judged scan, and only for `time_unknown`; with no judged scan before it, it records nothing `[Confirm]` 3.
- A scan older than one already judged for its device is stored but not judged, and a warning is logged `[Confirm]` 4.
- A changed limit is the same alarm: it keeps its state and is judged with the new row's limit and deadband, and the row ID in force is recorded.
- A level % threshold uses S-086's `tank_level` at the scan's time. A broken level configuration gives `unconfigured`; out of range gives `out_of_range`, while a raw threshold on signal 1001 still sees the overfill.
- An unclaimed device, overlapping assignments or overlapping thresholds record nothing for that scan and log an error. The scan is still stored.

## Test plan
pytest on SQLite with made-up tanks, devices, thresholds and readings, sent through `ingest_message` as CBOR with a fixed server clock a day after the scans, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases:
- A raise and a clear across the deadband, with no event while the value stays high.
- A redelivered message.
- An older scan stored after newer ones.
- Fault, stale-quality, aged, missing, untimed and clock-ahead readings between a raise and a clear.
- Untrusted readings from the start.
- A limit changed mid-stream.
- Level % raised, cleared and out of range, on an unconfigured tank and on a broken configuration.
- An unclaimed device and overlapping assignments.
- Overlapping thresholds.
- An untimed first scan.
- A failure in the step storing nothing.

## Out of scope
The read endpoint for alarms (S-091); acknowledgement (S-092); notifications; the dashboard; an admin endpoint for thresholds; re-judging stored history; retention and the S3 Object Lock copy; alarms on staleness itself; an on-delay; Phase 2 alarms; anything that commands a device; the TimescaleDB container, Cognito, Docker and Terraform.

## Open questions
1. `[Confirm]` Judging in the ingest transaction rather than a separate pass over stored scans: no cursor table and no scheduler, and an event is committed only with its scan. Two consumers ingesting one device at once could both read the same last state on Postgres. The queue story must deliver one device's messages in order, one at a time (for example a FIFO queue grouped by device), or the step takes a per-device lock.
2. `[Confirm]` A historic reading is judged by its own `age` and quality, not by how late it arrived. An alarm raised from a replayed backlog is a true past condition. Whether the device is live now is S-083's separate flag, which S-091 shows beside it.
3. `[Confirm]` An untimed scan moves the alarms of the tank at the device's newest judged scan to `cannot_evaluate`. If the device was moved before it rebooted, the old tank's alarms read "cannot evaluate". That is safe, because nothing is raised or cleared.
4. `[Confirm]` A late scan is not judged, because the append-only history cannot be rewritten. A device forwards its log oldest first, so this happens only if the queue reorders messages or the device's clock steps back. The scan's readings are still stored and shown.
5. `[Confirm]` No on-delay: P1-18 does not require one (S-087 `[Confirm]` 3). The deadband stops flapping.
6. `[Confirm]` Phase 1 has one device per tank. Two devices on one tank would feed the same alarms in turn.

## PR checklist notes
Title `feat(dashboard): record raised and cleared alarms in the backend (S-090)` (the `dashboard` scope, S-066 `[Confirm]` 1), `Closes #182`. A draft stacked on S-089 (#183): after #183 squash-merges, merge `develop` into this branch (no rebase, no force-push), then mark it ready. `interfaces/` and `.github/` unchanged.
