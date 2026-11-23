# P1-15: Synchronise device clocks so trends line up

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3. Points: 2. Priority: Must. Component: gateway and firmware (card); **now FRDM and ESP32 firmware**. Review flag: none.

## Goal
Every record carries a time that can be trusted and compared across devices.

## Phase check
Phase 1. Time handling only; no control implications.

## Decisions already made
- **ADR-0004 decision 11:** **SNTP** plus **boot-relative time** with a **boot ID** and a **"time not yet known" flag**. This is the whole mechanism — a device that has never reached an SNTP server still produces usable, ordered records that the cloud can place in time once a sync happens.
- **ADR-0006:** the ESP32 passes on time (SNTP) as part of its comms-helper role.
- **ADR-0008:** every value shown carries a quality flag and an age, so unsynchronised time must be visible to the dashboard, not hidden.

## Acceptance criteria (from the story card)
- All device clocks agree within the agreed limit `[Confirm limit, for example 1 s]`.
- The time source is documented.
- A clock error above the limit raises a **Warning**.
- Plus, from ADR-0004.11: records created before the first sync carry the "time not yet known" flag and the boot ID, and the cloud can reconcile them afterwards.

## Test plan
`native_sim` and simulator: normal sync, no SNTP server reachable at boot, SNTP reachable only after hours of buffering, clock step backwards during operation, boot ID changing across a power cycle. Check the Warning fires and that no record is ever silently given a wrong absolute time.

## Dependency
Pairs with P1-14 — buffering and time are the same problem seen from two sides. Do them together or adjacently.

## Out of scope
Any use of time for control or prediction (Phases 2 and 3).

## Open questions
- `[Confirm]` The agreement limit. 1 s is the card's example; NFR-01's 5 s freshness requirement suggests the limit should be well under that.
- `[Confirm]` Which SNTP source: the client's network, a public pool, or AWS?
- `[Confirm]` Who raises the Warning — the device, or the cloud on receipt?
