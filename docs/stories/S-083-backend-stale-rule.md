# S-083: Add the stale-reading rule in the backend

- Story ID: S-083 (issue #169).
- Epic: E4, the backend half of P1-19, part 1 of 2. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched; no new dependency. Chosen by the tech lead on 27 Nov 2026. Split from S-084, which serves the flag in the API, to keep each pull request under about 300 changed lines.

## Goal
Decide, for one stored reading and the server's clock, whether it is `live`, `stale` or `time-unknown`, so that no later endpoint or screen can show stale data as live (AGENTS.md section 7).

## Phase check
Phase 1, read-only for plant data. A pure judgement on values the device already sends: nothing is sent to a device, nothing is stored, no endpoint changes. No AI or analytics. No AWS resource or account (ADR-0007's three gates still hold).

## Decisions already made
- **ADR-0008 decision 6:** every value carries a quality flag and an age; the browser never talks to the broker. This story adds whether the value is still current; it changes neither.
- **ADR-0004 decision 11:** a scan whose wall-clock time is not known (`tk` false) is a distinct state from a device that has gone quiet (P1-19), so it gets its own state, `time-unknown`, and is never live.
- **interfaces/records.cddl:** `age` is the milliseconds from sampling a signal to the scan's `up`; quality code 1 `stale` means "last known value, not refreshed this scan".
- **interfaces/signals-v1.yaml:** `update_rate_ms` is 1000 for the 23 plant signals and 60 000 for the four device-health signals 9001 to 9004. The device sends one consolidated scan per second, in batches of five every 5 s (AGENTS.md sections 5 and 6).

## Files to create or change
- `backend/tankapi/liveness.py` (new): `Liveness`, `StaleRules`, `get_stale_rules`, `update_rate_ms`, `server_now`, `scan_liveness`, `reading_liveness`.
- `backend/tests/test_liveness.py` (new).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged; S-084 adds the field to the API.

## Acceptance criteria
The rule, applied in this order `[Confirm]` 1:
- `time-unknown` when the scan's time is not known, or when it is more than `clock_ahead_s` (default 2) ahead of the server clock, whatever the quality.
- `stale` when the scan is older, by the server clock, than the signal's update period plus `allowance_s` (default 14, so 15 s for a one-second signal and 74 s for a health signal); when the device's quality is `stale`; or when the reading's `age` is more than `age_factor` (default 2) update periods.
- `live` otherwise. A scan as a whole (`scan_liveness`, the silent-device check) is judged by the clock rules with the one-second scan period.
- The quality is never changed. `fault`, `unconfigured` and `out-of-range` readings follow the same time rule and keep their quality, so they can never be read as live good values.
- The three thresholds come from `TANKAPI_STALE_ALLOWANCE_S`, `TANKAPI_STALE_AGE_FACTOR` and `TANKAPI_CLOCK_AHEAD_S`, each falling back to its default when unset or empty. A value that is not one to six ASCII digits, or out of range, is refused with an error naming it. The update periods are the signal list's, checked by a test against `signals-v1.yaml`.
- "Now" is the server clock, `server_now`, passed in so tests can fix it.

## Test plan
pytest with a fixed clock, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: every signal's update period against `signals-v1.yaml`; a fresh reading live; 15 s and 15.001 s after a one-second scan; 74 s and 74.001 s for a health signal; `age` 2000 and 2001 ms; the device's own `stale` quality; an untimed scan with every quality; a scan 2 s and 3 s ahead of the server; `out-of-range`, `fault` and `unconfigured` live when fresh and stale when silent, unchanged; defaults, settings from the environment, malformed and out-of-range settings; the server clock.

## Out of scope
The API field and a latest-values endpoint (S-084). The dashboard's stale display (P1-21, P1-22), server-sent events and live push, alarms on staleness (P1-18), the "no data from device" cloud alert (ADR-0009), and the browser-to-backend disconnect, which only the browser can see (P1-19).

## Open questions
1. `[Confirm]` The thresholds: 15 s for a one-second signal (P1-19's open question: 5, 10 or 30 s; NFR-01's 5 s cannot hold with 5 s batches), two update periods of `age`, and 2 s of clock lead.
2. `[Confirm]` A signal the rule does not name (for example from a later signal list) gets the one-second period, so it turns stale soonest; per-version periods wait for a signal list that needs them.
3. `[Confirm]` A fresh `fault` reading is `live`: the fault is the current report. A client shows a value as live and good only when both fields say so.
