# S-077: Find when a device was on a customer's tanks

- Story ID: S-077 (issue #157).
- Epic: E4 (groundwork for P1-20). Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched.

## Goal
The readings endpoint can limit a whole time range to what one customer may see, in one query, by the same ownership rules as S-074's `owner_at`, which answers for one second at a time. Split out of the per-customer scoping story (S-078), which uses it, so each pull request stays near 300 changed lines.

## Phase check
Phase 1, read-only. Nothing is written, no endpoint changes and no device is contacted. No AWS resource and no account (ADR-0007's three gates still hold).

## Decisions already made
- **S-073:** an assignment puts a device on a tank over `[valid_from_unix_s, valid_to_unix_s)`; the row with no end is the current one; history is kept. **[Confirm] 4:** the schema cannot refuse overlap among closed rows, and a reader must not pick a customer when rows overlap.
- **S-074:** `owner_at(session, device_id, t)` gives the owner at one second and raises `OverlappingAssignmentsError` on overlap. **[Confirm] 3:** on overlap, show nothing and log the device ID.
- **S-073 [Confirm] 2** (recommended there, taken here and in S-078): a reading belongs to the customer whose tank the device was on at the scan's `t`.

## Files to create or change
- `backend/tankapi/ownership.py`: `Window` and `customer_windows`.
- `backend/tests/test_ownership.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` is not changed, no endpoint changes and there is no migration.

## Acceptance criteria
- `customer_windows(session, device_id, customer_id, start, end)` returns, oldest first, each `Window(start, end)` (`end` is `None` while it lasts) in which the device was on a tank of that customer and which reaches into `[start, end)`. It returns an empty list for an unknown device, an unclaimed one, another customer's, or a customer ID with no assignments.
- For every second `t` in `[start, end)`, `t` lies in a returned window exactly when `owner_at(session, device_id, t)` names that customer.
- A window keeps its assignments' own bounds, not the range's. Back-to-back assignments of the same customer (a move between its own tanks) form one window; a move to another customer, or a release, ends it.
- Any overlap among the device's assignments, open or closed, raises `OverlappingAssignmentsError` naming the device ([Confirm] 1).
- One query per call; nothing is written.

## Test plan
pytest on SQLite files migrated by Alembic, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. A timeline of four assignments (two tanks of customer 1, one of customer 2, a release, then customer 1 again): the joined windows with their own bounds, and empty results for a range off the customer, a customer with no assignments and an unknown device. Then, for 105 ranges built from the timeline's boundaries and three customers, the seconds inside the windows are exactly those where `owner_at` names the customer. Overlap: two closed rows that overlap, refused also for a range clear of the overlap, and an open row overlapped by a later closed one. No bench test: nothing touches hardware.

## Out of scope
Using it in the readings endpoint, untimed scans, gaps, and the 404 and 500 responses (S-078); the claim, move and release flow; the audit trail; per-plant and per-tank limits; users in our database.

## Open questions [Confirm]
1. **Any overlap refuses the device in every range** (recommended, taken). `owner_at` raises only at the overlapping seconds; `customer_windows` reads the device's whole history and refuses it, because a window must say whether a span of time lay wholly with one customer, and a broken history cannot. A device has few assignments, so reading them all costs little. Overlap is a fault the claim and move story must prevent; until an admin fixes it, no customer reads that device (S-078). The alternative, checking only the rows that reach into the range, matches `owner_at` exactly but can join or split a window through a broken row outside the range.
2. **Windows, not a join on every scan** (recommended, taken). Joining scans to assignments in SQL gives the same points, but repeats a scan once per overlapping row instead of refusing, and cannot tell whether a gap lay wholly with one customer.

## PR checklist notes
Title `feat(dashboard): find when a device was on a customer's tanks (S-077)`, branch `feature/S-077-backend-customer-windows`, `Closes #157`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. No migration and no new dependency.
