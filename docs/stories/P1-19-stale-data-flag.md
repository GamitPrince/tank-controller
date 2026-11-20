# P1-19: Show a stale-data flag when the gateway or cloud link drops

- Story ID: `[Confirm]` — not yet issued.
- Epic: E4. Points: 3. Priority: Must. Component: dashboard (backend). Review flag: none.

## Goal
A value that is no longer live is never shown as if it were.

## Phase check
Phase 1. This is the FR-SAF-04 requirement and one of the project's firmest rules: `AGENTS.md` section 7 — **never show stale data as live.**

## Decisions already made
- **ADR-0008:** every value carries a **quality flag and an age**; live updates by **server-sent events with a polling fallback**; the browser never talks to the broker; design uses **colour plus text**, so a stale marker must not be colour alone.
- **ADR-0004 decision 11:** the "time not yet known" flag is a distinct state from stale — a device that has never synced is not the same as a device that has gone quiet.
- **ADR-0009:** AWS monitoring includes a **"no data from device" alert**, which is the operational twin of this story's user-facing flag.

## Note on wording
The card says "when the **gateway** or cloud link drops". There is no gateway (ADR-0004.1). The states to detect are: device not publishing, ESP32 link down, cloud ingest behind, and browser-to-backend connection lost. Each needs its own treatment — a dropped browser connection must not be shown as a plant fault.

## Acceptance criteria (from the story card)
- Unplugging the device shows the stale-data flag **within 30 s**.
- Stale values are **labelled as stale**, with text as well as colour.
- The flag **clears** when data returns.
- Plus: distinguish device-quiet from browser-disconnected from clock-not-yet-known.

## Test plan
pytest and Vitest plus an end-to-end run against the simulator: pull the device link and time the flag, restore it and confirm clearing, drop the browser connection only, feed a device with the "time not yet known" flag, feed a failed-sensor quality flag. Playwright end-to-end covers the browser side and is not counted in the 80%.

## Dependency
P1-17 (ingest), and P1-21 or P1-22 for where the flag appears on screen.

## Out of scope
Alarm classes (P1-18). Predicting link loss (later phases).

## Open questions
- `[Confirm]` Staleness threshold. NFR-01 requires values under 5 s old when the link is up, while this story allows 30 s to show the flag — so what age makes a value stale: 5 s, 10 s, 30 s?
- `[Confirm]` Does a stale value stay visible with a marker, or get replaced by a dash?
