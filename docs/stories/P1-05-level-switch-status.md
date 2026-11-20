# P1-05: Read high-high and low-low level switches as status-only inputs

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2. Points: 3. Priority: Must. Component: firmware.
- **Review flag: EE must approve. `safety` label required. Any defect here is Critical.**

## Goal
Read the high-high level trip and low-low heater cut-off switch states and report them, without ever influencing them.

## Phase check
**Phase 1 safety boundary.** These are part of the hardwired safety chain. They are read as **status-only digital inputs**. No code may write to them, and no design may create a path that could. If anything in implementation looks like it could drive these, stop.

## Decisions already made
- **ADR-0002:** 16-channel **optocoupler digital inputs, status-only**, EE-designed, input-only by construction.
- **ADR-0003:** safety-status reads live in `firmware/src/safety/`, which is EE-owned in CODEOWNERS.
- **Channel assignment (EE, 20 Nov 2026):** **channel 1 = high-high level switch, channel 2 = low-low level switch.** Both at the pilot site.
- **Contact sense (decided 20 Nov 2026):** both are **normally closed**, so a de-energised device or a broken wire reads as *alarm*, never as healthy. Fail-safe for monitoring integrity.
- **Debounce (decided 20 Nov 2026):** **200 ms**, leaving about 4.8 s of the NFR-01 five-second budget for transmit, ingest and render. The EE's original 5 s figure is kept only for the equipment-status channels, where latency does not matter.

## Files to create or change
`firmware/src/safety/` — status read only. Changes here need the EE's approval and the `safety` label.

## Interfaces touched
Signal entries for the two switch states in `interfaces/`.

## Acceptance criteria (from the story card)
- High-high and low-low states reach the dashboard within 5 s.
- The inputs are read-only.
- **EE approval and the test result are recorded.**

## Test plan
`native_sim` with simulated optocoupler inputs: both states, transition, stuck input. Bench test with the EE on the real board, result recorded. End-to-end 5 s timing needs the cloud and dashboard path, so the full criterion cannot be proven until P1-12 and P1-19 exist — record the device-side latency here and the end-to-end figure later `[Confirm]`.

## Dependency
P1-03 (signal list). **No longer blocked** — the EE supplied the full channel inventory on 20 Nov 2026.

## Out of scope
Any output, relay, coil or acknowledgement path. Alarm logic (P1-18). The written no-write-path proof (P1-10).

## Open questions
- `[Confirm]` Is the 5 s criterion measured device-to-dashboard or device-to-cloud at this stage?
- `[Confirm]` Where is the EE's recorded test result stored? Hardware review records must **not** go in this public repo.
