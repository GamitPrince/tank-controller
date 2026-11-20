# P1-10: Prove and document that no output or write path reaches the hardwired safety chain

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2. Points: 2. Priority: Must. Component: firmware, hardware.
- **Review flag: EE signs the written record. `safety` label. Any defect here is Critical.**

## Goal
A written, EE-signed record showing that nothing in this project's hardware or software can write to the hardwired safety chain.

## Phase check
This story **is** the Phase 1 safety boundary check. It builds nothing; it proves a negative.

## Decisions already made
- `AGENTS.md` section 1 and ADR-0002: all three field interfaces are **input-only by design** (MAX31865 PT100, AD4111 4-20 mA, optocoupler digital inputs). RS-485 is not used in Phase 1.
- ADR-0004 decision 10 and `AGENTS.md`: the controller is **send-only**; the cloud never commands devices in Phase 1; the dashboard is read-only for plant data.

## Acceptance criteria (from the story card)
- Schematic and firmware review show no output, relay or coil connected to the safety chain.
- A simulated trip changes nothing in the safety chain from software.
- **The EE signs the written record.**

## CONFLICT — where the record lives
The story card puts the deliverable in `docs`, but `AGENTS.md` section 3 forbids committing **hardware schematics or hardware review records** to this public repo (decided 19 Nov; they live in a private location). So the signed record cannot go in `docs/safety/` as-is.

Suggested split, needs confirmation: a **public summary** in `docs/safety/` stating the review happened, its date, scope and outcome, with no schematic detail; the **signed record and schematics** held privately. `[Confirm]` with the tech lead and EE.

## Test plan
Desk review, not a build: trace every pin in the EE's pin mapping; search the firmware for any GPIO write, relay or output call in or near `firmware/src/safety/`; assert a simulated trip in `native_sim` and show no outbound write occurs. Record the method and the result.

## Dependency
Best done after P1-05 and P1-09 exist, so there is real code to review. Needs the EE's pin mapping, which is still outstanding (ADR-0002 unwritten).

## Out of scope
Changing any interface design. Phase 2 control hardware (Rev B board, relays).

## Open questions
- `[Confirm]` Public summary plus private signed record, as above?
- `[Confirm]` Who holds the private location, and what is the retention rule?
- `[Confirm]` Does this need repeating per hardware revision?
