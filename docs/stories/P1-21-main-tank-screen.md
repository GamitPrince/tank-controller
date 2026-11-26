# P1-21: Main tank screen

- Story ID: `[Confirm]` — not yet issued.
- Epic: E5 Dashboard. Points: 8 (the largest story in Phase 1). Component: dashboard. Review flag: none.

## Goal
The screen an operator looks at: tank graphic, level, volume, temperatures, equipment status, alarm banner.

## Phase check
Phase 1. **The dashboard is read-only for plant data and never sends a command to a device.** The card says "controls are large enough to use on a tablet with gloves" — read as *interactive elements* (navigation, acknowledgement, range selection), not plant controls.

## Signal availability — mostly resolved 20 Nov 2026
The card asks for "tank graphic, level, volume, temperature, **heater, pump and valve status**, alarm banner, **dispatch readiness**". The EE's channel inventory confirms most of it **does** exist:

| Card item | Available? |
| --- | --- |
| Level | Yes — radar level on the AD4111 (P1-04) |
| Temperature | Yes — six product PT100s, two per level at 180 degrees (P1-06). **Not** the card's six named zones |
| Heater status | **Yes** — channels 8 and 9, base heater and main heater on/off |
| Pump status | **Yes** — channels 4 and 5, inlet and outlet pump status, plus the dry run alarm |
| Valve status | **Yes** — channels 3 and 6, inlet and outlet valve status |
| Mixture motor | **Yes** — channel 7, not asked for by the card but available |
| Alarm banner | Yes — six alarm contacts plus the two level switches |
| Volume | **Computed in the cloud** (ADR-0004.10), so it depends on the P1-04 split |
| Dispatch readiness | **Still undefined.** The card's question 5 assumes "product temperature inside a set band" |

Still absent, so the screen must not imply them: **over-temperature trip, emergency stop, fire or gas, ambient temperature, wind**. Over-temperature and e-stop exist at site but are not wired to this board — if an operator expects to see them, that is a gap to raise with the client.

## Decisions already made
- **ADR-0008:** TypeScript and React; OpenAPI with generated TypeScript types; **server-sent events** with a polling fallback; **quality flag and age on every value**; the browser **never** talks to the broker; **Vitest** with React Testing Library; the 80% gate counts all code **including screens**; Playwright end-to-end is not counted; static SPA on AWS storage plus CDN; **colour plus text**; tablet usable with gloves.

## Acceptance criteria (from the story card)
- Every listed item is present — **pending the conflict above**.
- Values are **less than 5 s old** when the link is up (NFR-01).
- Active alarms show in the banner.
- Interactive elements are large enough for a tablet with gloves.
- Plus: every value shows its quality flag and age; stale values are marked (P1-19).

## Test plan
Vitest for components and data binding; Playwright end-to-end against the simulator for the live path, the 5 s freshness figure and the stale marker. Glove and tablet usability is a human check against the P1-26 designs, recorded.

## Dependency
P1-03 (signals), P1-17 (data), P1-19 (stale), P1-22 (colour code), **P1-26 (designs, due in sprint 3 so this can start)**, and the dashboard owner question.

## Out of scope
Trends, CSV and PDF (P1-23). Any AI recommendation element (P1-22 forbids it in Phase 1). Any control.

## Open questions
- `[Confirm]` What does "dispatch readiness" show?
- `[Confirm]` How are the paired PT100s at each level presented? Two values per level, or one per level? Averaging them would be a comparison, and comparison is Phase 2 — so showing both is the safe reading.
- `[Confirm]` Should the screen state that over-temperature and e-stop are not monitored, so an operator does not assume silence means healthy?
- **Owner: GamitPrince** (decided 26 Nov 2026). ADR-0008's context still names ArkinGamit and SHINE-18, who have left; S-054 corrects it.
