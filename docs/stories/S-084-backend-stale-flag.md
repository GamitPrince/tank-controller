# S-084: Flag stale readings in the backend

- Story ID: S-084 (issue #171).
- Epic: E4, the backend half of P1-19, part 2 of 2. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched; no new dependency. Chosen by the tech lead on 27 Nov 2026. Builds on S-083 (issue #169), which holds the rule.

## Goal
Give a live view each signal's newest value with a flag saying whether it is still live, so the dashboard can never show stale data as live (AGENTS.md section 7).

## Phase check
Phase 1, read-only for plant data. One more GET endpoint; nothing is sent to a device and nothing is written except the existing service audit row. No AI or analytics. No AWS resource or account (ADR-0007's three gates still hold). No dashboard screen.

## Decisions already made
- **S-083:** `tankapi.liveness` judges a reading `live`, `stale` or `time-unknown` against the server clock, with thresholds from environment settings and update periods from the signal list. Quality is never changed.
- **ADR-0008 decisions 3 and 6:** the backend checks every request; every value carries a quality flag and an age; live updates come by server-sent events with polling as the fallback, so a polled endpoint comes first.
- **S-078:** a customer's caller sees only scans taken while the device was on their tanks, no untimed scan, and the unknown device's 404 for anything else. **S-080:** every service `/v1` request is audited.

## Files to create or change
- `backend/tankapi/latest.py` (new): `GET /v1/devices/{device_id}/latest`, `Latest`, `LatestValue`.
- `backend/tankapi/main.py`: mount the router under `/v1`.
- `backend/tankapi/readings.py`: `_windows` and `_within` made public as `caller_windows` and `within_window`, unchanged otherwise, so both endpoints scope the same way.
- `backend/tests/test_latest.py` (new).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI document gains the endpoint and the `Liveness` enum. `interfaces/` is unchanged.

## Acceptance criteria
- A live view gets a polled endpoint of its own, not a field on the trend query `[Confirm]` 1. For each signal it returns the newest reading the caller may see, taken from the 120 s up to the newest timed scan, so a once-a-minute health signal is found. Each reading has its time, boot ID, sequence, signal-list version, quality, age and value as stored, plus `liveness`.
- `device` is `time-unknown` when the device's newest stored scan has no known time, whatever the older scans say. Otherwise it is the S-083 state of the newest timed scan the caller may see, or `stale` when there is none. `server_time` and `last_t` are returned too.
- A value that is no longer current is returned with its flag, never left out and never `live` `[Confirm]` 2. A value from an untimed scan is never returned.
- `fault`, `unconfigured` and `out-of-range` keep their quality; a fault has no value.
- A customer's caller sees the device only while it is on one of their tanks now, and only scans from the current stretch of that ownership `[Confirm]` 3. Anything else gives `404 {"detail": "not found"}`, as an unknown device does. Service sees every scan.
- GET only. Every service request is audited by the existing `/v1` router; a customer's is not.

## Test plan
pytest on a fixed clock (`server_now` and `get_stale_rules` overridden), locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: fresh values live, with fault, unconfigured, out-of-range and a once-a-minute signal; 15 s and 15.5 s after the last scan; the device's `stale` quality; untimed scans only, and an untimed scan after a timed one, for service and for a customer; another customer, a never-claimed device, an unknown device and a released device all 404; no scan from before a claim; one audit row for service and none for a customer; the OpenAPI path, enum, description and required fields.

## Out of scope
The dashboard's stale display (P1-21, P1-22), server-sent events and live push, alarms on staleness (P1-18), the "no data from device" cloud alert (ADR-0009), the browser-disconnected state (the browser's own), and a faster latest-value query on TimescaleDB.

## Open questions
1. `[Confirm]` A separate latest-values endpoint rather than a liveness field on every trend point of the readings endpoint.
2. `[Confirm]` A stale value is returned with its marker (P1-19's open question on marker or dash); the screen decides how to draw it.
3. `[Confirm]` A customer sees a device's latest values only while it is on their tank now. A customer that just claimed a device sees `stale` with no values until its first scan arrives. A device whose clock is not set shows them `time-unknown` without any untimed value.
