# P1-07: Read heater sheath, heater pocket and thermal-oil inlet/outlet temperatures — **VOID**

- Story ID: none. **Do not create an issue for this story.**
- Epic: E2. Points: 3 — **return these to the backlog.**
- Status: **VOID as of 20 Nov 2026.** Kept as a record of why, not as work to do.

## Why this story is void
The EE confirmed the installed instrumentation on 20 Nov 2026:

- **No thermal-oil circuit exists** at the pilot site, so there are no thermal-oil inlet or outlet temperatures to read.
- **Only six PT100s are installed** and all six are product temperatures (two upper, two middle, two bottom, at 180 degrees). There are **no heater sheath or heater pocket PT100s**, and no spare MAX31865 channels to add any.

All four signals this story was written for therefore do not exist in Phase 1.

## What replaces it
Nothing. Heater state is covered differently and already: the digital inputs include **base heater on/off** and **main heater on/off** (channels 8 and 9, see P1-03), and the **low mixture temperature alarm** (channel 14). Those are read under P1-09 and shown under P1-21.

## Consequences to carry elsewhere
1. **Backlog:** Phase 1 drops from 27 stories to 26, and E2 from 23 points to 20. The story card is a Claude Doc owned by the project manager and has not been changed.
2. **`AGENTS.md` section 5** still lists "heater sheath/pocket and thermal-oil inlet/outlet temperatures" as Phase 1 signals. It is wrong and needs a PR.
3. **RSD FR-TMP-02** is the requirement behind this story. If the requirement stands but the hardware does not exist, FR-TMP-02 needs rewording or moving to a later phase — a project-manager decision.

## If this is reopened
It would need new sensors, a second MAX31865 or spare AD4111 channels, an ADR-0002 amendment and the EE's sign-off. Treat it as new work, not as this story resumed.

## Open questions
- `[Confirm]` Reword or re-phase RSD FR-TMP-02?
- `[Confirm]` Is heater performance monitoring wanted in Phase 2, and if so does it need these sensors fitted then?
