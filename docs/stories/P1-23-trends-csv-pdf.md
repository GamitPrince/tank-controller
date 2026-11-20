# P1-23: Trend charts with CSV export and PDF reports

- Story ID: `[Confirm]` — not yet issued.
- Epic: E5. Points: 5. Priority: **Should** — the card says this may slip if sprint 4 is overloaded. Component: dashboard. Review flag: none.

## Goal
Look back over time, export the numbers, and produce a report for a tank and period.

## Phase check
Phase 1. Reading history only; no prediction or analytics (Phases 3 and 4).

## Decisions already made
- **ADR-0008:** TypeScript and React; OpenAPI generated types; **CSV export** is named in the ADR; Vitest; 80% gate counts screens.
- **ADR-0007:** retention sets what history exists — **per-second for 90 days, per-minute summaries forever, raw archive forever**. A trend over more than 90 days therefore shows per-minute data, which the UI must make clear rather than silently changing resolution.
- **ADR-0008:** every value carries a quality flag and age, so exported data should carry quality too.

## Gap worth noting
**PDF reports are not mentioned in ADR-0008**, which names only CSV export. Generating PDFs needs a library and a decision about server-side or client-side rendering, neither of which is recorded. Treat PDF as the part of this story most likely to be cut, consistent with its Should priority.

## Acceptance criteria (from the story card)
- Any signal can be trended over a chosen period.
- **CSV export matches stored values** — exactly, including quality flags and the calculation version for computed values (ADR-0007).
- A PDF report is produced for a chosen tank and period.
- Plus: when the period crosses the 90-day per-second boundary, the chart states which resolution it is showing.

## Test plan
Vitest for the chart component and range handling; a backend test that CSV output matches a known stored series byte for byte; a period spanning the retention boundary; an export of a series containing failed-sensor gaps, confirming gaps are gaps and not interpolated.

## Dependency
P1-17 (stored data and retention), P1-21 (navigation), P1-22 (colour code).

## Out of scope
Scheduled or emailed reports. Cross-tank or fleet comparison (Phase 4). Any trend-based alarm or prediction.

## Open questions
- `[Confirm]` Is the PDF report required in Phase 1, or can it move to Phase 2 given it has no ADR?
- `[Confirm]` Server-side or client-side PDF rendering, and which library?
- `[Confirm]` Maximum period and point count for a single chart.
