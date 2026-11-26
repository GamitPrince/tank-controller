# P1-26: Design the dashboard screens in Figma

- Story ID: `[Confirm]` — not yet issued.
- Epic: E5 (scheduled in sprint 3 so P1-21 can start against it). Points: 3. Priority: Must. Component: dashboard. Review flag: none.

## Goal
Agreed designs for the main tank screen, trend view, login and alarm banner, before the screens are built.

## Phase check
Phase 1. Design only. The designs must not show controls that command plant equipment, and must not include the Phase 3 AI recommendation element.

## Decisions already made
- **ADR-0008:** TypeScript and React; **colour plus text**, never colour alone; **tablet usable with gloves**; roles operator, maintenance, admin, service; quality flag and age shown on every value; the dashboard is read-only for plant data.
- `AGENTS.md` NFR-08 and plant facts: hot, dusty, bright outdoor site — so contrast and glare matter, and so does glove-sized touch targets.
- Tooling stays free-first per the playbook; Figma is named in the card.

## Deliverables
- Main tank screen, trend view, login, alarm banner.
- The colour code (green, amber, red, grey) with text labels, feeding P1-22's token values.
- A tablet layout sized for gloved use.
- Designs **linked from docs** — a link, not an export, since large binaries must not be committed.

## Acceptance criteria (from the story card)
- Designs exist for all four screens and are linked from docs.
- The colour code and text labels on alarms are shown.
- Controls are sized for tablet use with gloves.
- **The dashboard developer and an operator representative have reviewed them** `[Confirm reviewers]`.

## Blockers
1. **No dashboard developer.** ADR-0008's context names ArkinGamit and SHINE-18, who left on 20 Nov 2026. Since 26 Nov 2026 GamitPrince builds the dashboard; one approval from a collaborator other than the author reviews the designs.
2. **No operator representative identified.** This needs the client, and it is the kind of review that cannot be done internally — an operator who works the plant with gloves on is the whole point.
3. **P1-21's signal conflict** feeds back here: the designs should not show heater, pump or valve status if Phase 1 has no such signals. Settle that before drawing tiles for them.

## Dependency
Should precede P1-21 and P1-22. Depends on the P1-03 signal list for what can actually be shown.

## Out of scope
Building the screens (P1-21 to P1-23). A design system or component library unless asked. Phase 2 control screens.

## Open questions
- **Resolved 26 Nov 2026:** GamitPrince builds the dashboard and designs; one non-author collaborator reviews them.
- `[Confirm]` Can the client provide an operator to review, and when?
- `[Confirm]` Is Figma still the tool, given the team shrank?
