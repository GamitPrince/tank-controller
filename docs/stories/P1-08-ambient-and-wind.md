# P1-08: Read ambient temperature and wind input — **VOID**

- Story ID: none. **Do not create an issue for this story.**
- Epic: E2. Points: 2 — **return these to the backlog.** Priority was Should.
- Status: **VOID as of 20 Nov 2026.** Kept as a record of why.

## Why this story is void
The EE confirmed on 20 Nov 2026:

- **No ambient temperature measurement.** All six MAX31865 channels are used by product PT100s and no others are installed.
- **No wind sensor.**

Both signals this story was written for do not exist in Phase 1. Nothing is read, so there is nothing to build.

## Note
This was the only **Should** in E2, so dropping it costs nothing against the Must set. Two AD4111 4-20 mA channels remain free, so ambient could be added later as a transmitter without touching the PT100 design — but that is new work needing an ADR-0002 amendment, not this story.

## Consequences to carry elsewhere
1. **Backlog:** with P1-07 also void, Phase 1 drops to 25 stories and E2 to 18 points.
2. **`AGENTS.md` section 5** lists "ambient (and wind if fitted)" as Phase 1 signals. Wrong; needs a PR.
3. **RSD FR-TMP-03** is the requirement behind this story and now has no implementation. Reword or re-phase it — a project-manager decision.
4. **Phase 3 impact worth noting:** predictive heating and energy optimisation would normally use ambient temperature. Deciding now that ambient is not measured means Phase 3 will either need it fitted later or will work without it. Worth recording deliberately rather than discovering in Phase 3.

## Open questions
- `[Confirm]` Reword or re-phase RSD FR-TMP-03?
- `[Confirm]` Should ambient be added on a spare AD4111 channel for Phase 3's benefit, even though Phase 1 does not need it?
