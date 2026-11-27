# S-078: Limit readings to the caller's customer

- Story ID: S-078 (issue #158).
- Epic: E4 (P1-20). Points: 3. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched. Built on S-077 (#157), which merges first.

## Goal
A caller of one customer cannot read another customer's readings by any request, including by guessing device IDs (P1-20's multi-tenant isolation test). This closes the gap S-075 [Confirm] 2 left open, where any valid token read any device.

## Phase check
Phase 1, read-only. The change only narrows what `GET /v1/devices/{device_id}/readings` returns: nothing is written and no device is contacted. No Cognito user pool, no AWS resource and no account (ADR-0007's three gates still hold). Tests generate their keys at run time and make no network call, and every customer, plant, tank and device name in them is made up.

## Decisions already made
- **ADR-0007 decision 2:** one shared multi-tenant cloud, customer > plant > tank > device; customers never see each other's data.
- **ADR-0008 decision 3:** the backend checks every request; service is our own staff, may support any customer, and every such access is audited.
- **S-076:** the role comes from `cognito:groups`, the customer from `custom:customer_id`, and a service caller has no customer. Its [Confirm] 1 left an unknown customer ID to this story: it has no assignments, so it sees nothing.
- **S-073 [Confirm] 2 and 3** (recommended there, taken here): a reading is shown only to the customer whose tank the device was on at the scan's `t`, so readings from before a claim or after a release are shown to nobody; a scan with no known time is shown to no customer.
- **S-073 [Confirm] 4, S-074 [Confirm] 3:** overlapping assignments are refused, never guessed, and the device ID is logged.
- **S-077:** `customer_windows` gives a customer's stretches of a device for a whole range, by `owner_at`'s rules, and refuses any overlap.

## Files to create or change
- `backend/tankapi/readings.py`: the caller, the filters, `untimed` null for customers, the fixed 404 and 500.
- `backend/tankapi/auth.py` (module docstring only).
- `backend/tests/test_isolation.py` (new: P1-20 asks for its own file), `backend/tests/test_readings.py` (S-072's tests now run as service).
- `backend/README.md`, `docs/stories/S-075-backend-token-check.md` (its [Confirm] 2 only), `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
`interfaces/` is not changed. In the generated OpenAPI document, `untimed` may now be null ([Confirm] 2), and every 404 has the body `{"detail": "not found"}` ([Confirm] 3).

## Acceptance criteria
- **Service:** S-072's response for every device, whatever its assignments: scans before a claim and after a release, untimed counts, and records from devices missing from `devices`.
- **Operator, maintenance and admin:** points only for scans whose `t` lies in a window of their customer; `untimed` is null; a gap only when both its ends' times are known and lie in one window, and it overlaps the range by S-072's rule ([Confirm] 1).
- No window reaching into the range, or no records stored, gives 404 `{"detail": "not found"}`, the same status, body and headers as for an unknown device.
- Overlapping assignments give a customer's caller 500 `{"detail": "server error"}`, logged at error level with the caller's `sub` and the device ID, never the token ([Confirm] 4).
- The 422 checks come first and are the same for every caller; the point limit counts only the caller's points. No role reads more than another.

## Test plan
pytest with FastAPI's `TestClient` on SQLite files migrated by Alembic, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, in `test_isolation.py`. Two made-up customers with a device each, scanning every 5 s from 10 s before the claim. Each customer role sees its own device and gets 404 for the other's; service sees every device whole. Another customer's device, a never-claimed one, one with no device row, the caller's own before its claim, and an unknown one all give identical 404 responses. A move to the other customer mid-range shows each its own part; a release hides the rest. An untimed scan and gap are withheld (null) from customers and counted for service. There are gaps before the claim, in each customer's time, across the move and with an unknown end, and a move between a customer's own tanks hides nothing. Overlapping assignments give the fixed 500, logged without the token, while service still reads. `test_readings.py` keeps S-072's tests, run as service. No bench test: nothing touches hardware.

## Out of scope
The audit trail for service access, and so any deployment; per-plant and per-tank limits; users in our database; the claim, move and release flow; what ingest does with records from unknown or unclaimed devices; per-role permissions; the Cognito user pool, its trigger and Terraform; sign-in screens; the Docker image; the dashboard.

## Open questions [Confirm]
1. **A customer sees a gap only when it lies wholly in one of its windows** (recommended, taken). The brief's example, every gap that overlaps the customer's time, would show the boot ID, sequence and time of a scan that is not theirs for a gap across a move or a release, and a gap with an unknown end may reach outside. The cost: such a gap is shown to service only. The points on both sides still show the hole, just not why.
2. **`untimed` is null for a customer's caller** (recommended, taken). Zero would claim there are none, and a real count could include another customer's scans or bench tests from before the claim. Null means "not reported to you". Placing untimed scans (S-072 [Confirm] 2) would let a later story count a customer's own.
3. **A device the caller cannot see is 404 with the unknown device's body** (recommended, taken). The S-072 body named the device and said nothing was stored; every 404 is now `{"detail": "not found"}`. A 403 would tell a prober that the ID exists.
4. **Overlap is 500** (recommended, taken), body `{"detail": "server error"}`: our data fault, not the caller's, and not temporary, so 503 would invite retries. It differs from a 404, so it tells anyone that the ID has broken assignments, but no reading or customer; the claim and move story must make overlap impossible.
5. **Service is never limited or refused** (recommended, taken), not even on overlap, because it does not ask who owned the device. **Service access is audited by S-080** (ADR-0008 decision 3). The API still stays local-only until what S-080's spec lists as blocking deployment is done.

## PR checklist notes
Title `feat(dashboard): limit readings to the caller's customer (S-078)`, branch `feature/S-078-backend-customer-scoping`, `Closes #158`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. No migration and no new dependency. Built on S-077 (#157): rebase onto `develop` once that merges.
