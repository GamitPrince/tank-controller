# P1-27: Read valve, pump, mixture motor and heater status as status-only inputs

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2 Field sensing. Points: **3 (proposed)**. Priority: Must. Component: firmware.
- Review flag: **none.** These are not safety-chain reads — see "Why this is not a safety story".
- **This story is not on the Phase 1 Story Cards document.** It was added on 20 Nov 2026 after the EE supplied the digital channel inventory, which contains seven equipment-status signals the backlog never knew existed.

## Goal
Read the seven plant equipment status contacts and report each as a status-only input with a quality flag.

## Phase check
Phase 1, read-only. We report whether equipment is running. We never start, stop or command any of it — valve and pump **control** is Phase 2 and needs the Rev B board.

## Why this story exists
The story card (26 Oct 2026) was written before the digital channel list was shared. It allocated channels 1 and 2 to P1-05 and the trip contacts to P1-09, but **seven channels were left with no story**:

| Ch | Signal | Contact sense | Debounce |
| --- | --- | --- | --- |
| 3 | Inlet valve status | Normally open | 5 s |
| 4 | Inlet pump status | Normally open | 5 s |
| 5 | Outlet pump status | Normally open | 5 s |
| 6 | Outlet valve status | Normally open | 5 s |
| 7 | Mixture motor on/off | Normally open | 5 s |
| 8 | Base heater on/off | Normally open | 5 s |
| 9 | Main heater on/off | Normally open | 5 s |

These are what make the main tank screen (P1-21) possible: the story card asked for heater, pump and valve status, and these channels are where it comes from.

## Why this is not a safety story
Channels 3 to 9 report **equipment running state**, not trips or interlocks. They are not part of the hardwired safety chain, so:

- They do **not** go in `firmware/src/safety/`, which is reserved for safety-chain status reads and is EE-owned in CODEOWNERS.
- They do **not** need the `safety` label or the EE's approval.
- They belong in the ordinary measurement layer alongside the PT100 and 4-20 mA reads.

`[Confirm]` this placement with the tech lead before coding. Getting it wrong in either direction is costly: putting them in `firmware/src/safety/` makes every future change need the EE, while wrongly excluding a genuine safety signal would evade a required review.

Note the deliberate asymmetry in contact sense: these seven are **normally open**, so open simply means "not running", which is correct and unambiguous for equipment state. The eight safety and alarm channels are normally closed so that a broken wire reads as alarm. Do not "harmonise" the two.

## Decisions already made
- **ADR-0002:** 16-channel optocoupler digital inputs, status-only, input-only by construction.
- **ADR-0003:** four firmware layers; hardware layer counts towards the 80% coverage gate; simulated inputs on `native_sim`.
- **Contact sense and debounce, decided 20 Nov 2026:** normally open, 5 s debounce. 5 s is deliberate here — contactor chatter is common on motor and pump starts, and latency does not matter for a running state the way it does for an alarm.

## Files to create or change
`firmware/src/` measurement layer, reusing the optocoupler input reading built for P1-05 and P1-09. Signal entries in `interfaces/`.

## Interfaces touched
Seven signal entries in the YAML signal list. Needs one non-author collaborator's approval and `interfaces-review` green.

## Acceptance criteria
- All seven states are read and reported, each with a quality flag.
- Debounce is 5 s, configurable, not hardcoded.
- Contacts are read with the normally-open sense: closed means running.
- A state change is reported within the configured scan and debounce window.
- Unit test coverage at or above 80%.

## Test plan
`native_sim` with simulated optocoupler inputs: each channel on and off, all seven at once, contact chatter shorter than 5 s (must be suppressed), chatter longer than 5 s (must be reported), a channel held in an intermediate state. Bench test on real inputs recorded with P1-25.

## Dependency
P1-03 (signal list). Best done after P1-05 or P1-09, so the optocoupler reading already exists and this story is mostly signal definitions and tests.

## Out of scope
Any command to a valve, pump, motor or heater — Phase 2. Run-hour counting, duty-cycle or efficiency analytics — Phase 2 and 3. Inferring a fault from a status (for example "pump on but no flow") — that is a cross-signal check and therefore Phase 2.

## Open questions
- `[Confirm]` Story points. 3 is proposed on the basis that the input driver already exists from P1-05 and P1-09.
- `[Confirm]` Placement outside `firmware/src/safety/`, as argued above.
- `[Confirm]` Do the two heater states (base, main) need to pair with the low mixture temperature alarm on the screen? That would be a cross-signal relationship, so Phase 1 shows them side by side without drawing a conclusion.
