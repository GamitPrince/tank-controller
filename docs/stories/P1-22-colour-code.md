# P1-22: Apply the colour code, with text as well as colour on alarms

- Story ID: `[Confirm]` — not yet issued.
- Epic: E5. Points: 3. Priority: Must. Component: dashboard. Review flag: none.

## Goal
One consistent visual language for state, readable without relying on colour.

## Phase check
Phase 1. The card is explicit: **no blue AI-recommendation element appears in Phase 1.** That blue element belongs to Phase 3 and must not be built early.

## Decisions already made
- **ADR-0008:** design uses **colour plus text**; tablet usable with gloves; the 80% coverage gate counts screens.
- `AGENTS.md` NFR-08: screens must not rely on colour alone.

## Colour code
Green, amber, red, grey — grey being the stale or unknown state, which ties this story to P1-19.

## Acceptance criteria (from the story card)
- Colours match the code.
- **Every alarm shows a text label as well as colour.**
- **No blue AI-recommendation element appears in Phase 1.**
- Plus: the palette is defined once as tokens, not repeated per component (no hardcoded values, `AGENTS.md` section 7).

## Test plan
Vitend/Vitest snapshot and assertion tests that each state renders its text label; a contrast check against the chosen values; a colour-blindness simulation pass on the four states; confirm grey is used for stale and unknown and nothing else.

## Dependency
P1-26 (designs define the actual colour values) and P1-19 (grey state).

## Out of scope
The Phase 3 recommendation element. Theming or dark mode unless the designs call for it `[Confirm]`.

## Open questions
- `[Confirm]` The exact colour values — they come from the P1-26 Figma designs.
- `[Confirm]` What does amber mean precisely: Warning class only, or also Advisory?
- `[Confirm]` Is a dark or high-brightness outdoor mode wanted? The site is a hot, bright outdoor plant.
