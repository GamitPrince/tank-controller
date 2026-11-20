# P1-09: Read alarm and trip status as status-only inputs

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2. Points: 3. Priority: Must. Component: firmware.
- **Review flag: EE must approve. `safety` label required. Any defect here is Critical.**
- Status: **Scope reduced** by the EE's inventory of 20 Nov 2026.

## Goal
Report the state of each alarm and trip contact that reaches the board, as a status-only input.

## Phase check
**Phase 1 safety boundary.** These contacts come from field devices that carry their own safety mechanisms. We **read only**. No reset, no acknowledge-to-device, no bypass, no output. If implementation appears to need any of those, stop and ask.

## SCOPE CHANGE — what this story actually covers now
The story card titled this "over-temperature, emergency-stop and pump dry-run trip status, and fire or gas where fitted". The EE confirmed on 20 Nov 2026 that **over-temperature and emergency stop exist at the site but are not routed to this board**, and there is **no fire or gas** installation.

| Card signal | Reality |
| --- | --- |
| Over-temperature trip | **Not routed to the board.** Handled at site |
| Emergency stop | **Not routed to the board.** Handled at site |
| Pump dry-run | **Channel 15, dry run alarm** |
| Fire or gas | **Not fitted** |

So this story now covers the six alarm contacts that do reach us:

| Ch | Signal | Contact sense | Debounce |
| --- | --- | --- | --- |
| 10 | Low pressure level alarm | Normally closed | 200 ms |
| 11 | High pressure level alarm | Normally closed | 200 ms |
| 12 | Low radar level alarm | Normally closed | 200 ms |
| 13 | High radar level alarm | Normally closed | 200 ms |
| 14 | Low mixture temperature alarm | Normally closed | 200 ms |
| 15 | Dry run alarm | Normally closed | 200 ms |

Channels 1 and 2 (high-high and low-low level switches) stay with **P1-05**. The seven equipment-status channels (3 to 9) are **not** in this story and are not safety reads — they need their own story, which does not exist yet. See the open questions.

## Decisions already made
- **ADR-0002:** 16-channel optocoupler digital inputs, status-only, input-only by construction.
- **ADR-0003:** safety-status reads live in `firmware/src/safety/`, EE-owned in CODEOWNERS.
- **Contact sense, decided 20 Nov 2026:** all six are **normally closed**, so a de-energised device or a broken wire reads as *alarm*. Fail-safe for monitoring integrity.
- **Debounce, decided 20 Nov 2026:** 200 ms, leaving about 4.8 s of the NFR-01 five-second budget for transmit, ingest and render.

## Files to create or change
`firmware/src/safety/` only. EE approval and `safety` label required.

## Acceptance criteria
- Each of the six alarm states is reported within the latency budget; device-side latency recorded here, end-to-end verified once the cloud path exists.
- Contacts are read with the **normally-closed** sense, so an open circuit reports as alarm, never as healthy.
- Debounce is 200 ms and configurable, not hardcoded.
- Over-temperature, emergency stop and fire/gas are **absent**, not reported as healthy.
- **EE approval and the test result are recorded.**

## Test plan
`native_sim` with simulated optocoupler inputs: each alarm asserted and cleared, several at once, open circuit (must read as alarm), contact chatter shorter than the debounce, chatter longer than it. Bench test with the EE on real inputs, result recorded.

## Dependency
P1-03 (signal list). No longer blocked — the inventory is complete.

## Out of scope
Alarm classes, acknowledgement and audit trail (P1-18; acknowledgement happens in the cloud, never to the device). Equipment status channels 3 to 9. Any automatic action.

## Open questions
- `[Confirm]` **Which story reads the seven equipment-status channels (3 to 9)?** They are not safety reads, so they do not belong in `firmware/src/safety/` and they are not in P1-05 or P1-09. A new story is needed, or P1-09 widens and splits its folder placement.
- `[Confirm]` Do over-temperature and e-stop need to reach the dashboard at all? If an operator expects to see them and they are not wired, that is a gap worth stating to the client, since the spare channel 16 could carry one of them.
- `[Confirm]` Where the EE's recorded test result is stored, given hardware review records stay out of this public repo.
