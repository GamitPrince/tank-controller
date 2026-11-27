# S-074: Resolve a device to its tank, plant and customer

- Story ID: S-074 (issue #151).
- Epic: E4 (groundwork for P1-20). Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
Given a device ID, the backend can say which tank, plant and customer the device is on, either now or at a given Unix time. Otherwise it says the device is unclaimed at that time, or unknown. The login story (P1-20) needs this answer before it can limit a request to one customer's data. The helper was written in S-073 and split out to keep that PR small.

## Phase check
Phase 1, read-only. One module of read queries. There is no endpoint, no write and no claim flow. Nothing is sent to a device. No cloud account and no AWS resource are used (ADR-0007's three gates still hold). Tests run on local SQLite files with made-up names.

## Decisions already made
- **ADR-0007 decision 2:** every user, query and device is held to its own customer. **ADR-0008 decision 3:** the backend checks this on every request.
- **ADR-0005 decision 2:** a device is unclaimed until an admin assigns it to a tank. Its data is held and not shown.
- **S-073:** an assignment puts a device on a tank over `[valid_from_unix_s, valid_to_unix_s)`, in Unix seconds UTC, the time base of a scan's `t`. The row with no end is the current assignment, and there is at most one. [Confirm] 1, 5 and 7 are confirmed: assignments keep history, IDs are integers, and claim state comes from the assignments, not from a flag.
- **S-073 [Confirm] 3:** a scan with no known time cannot be placed in an assignment. **[Confirm] 4:** if rows overlap, the read helper raises instead of picking a customer.

## Files to create or change
- `backend/tankapi/ownership.py`: `Owner`, `Unowned`, `OverlappingAssignmentsError`, `owner_now`, `owner_at`.
- `backend/tests/test_ownership.py`: the resolver tests, using S-073's fixtures.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`, and the out-of-scope note in `S-073-backend-ownership-tables.md`.

## Interfaces touched
None. `interfaces/` is not changed, and there is no migration.

## Acceptance criteria
- `owner_now(session, device_id)` uses the device's open assignment. `owner_at(session, device_id, unix_time_s)` uses the assignment that held at that second. Both return `Owner(customer_id, plant_id, tank_id)`, `Unowned.UNCLAIMED` for a device in `devices` that is on no tank at that time, or `Unowned.UNKNOWN` for a device not in `devices`.
- The start of an assignment is included and its end is excluded. At the instant of a move, the device is on the new tank. At the instant of a release, it is unclaimed.
- A moved device resolves to its old tank for any time before the move.
- If more than one assignment holds at that time, `OverlappingAssignmentsError` is raised, and no owner is returned.
- `owner_at` takes only whole Unix seconds. `None`, a bool or a float raises `TypeError`, so an untimed scan can never be placed on the current tank by its arrival time.
- Nothing writes. `ingest_message`, `store_message`, the readings endpoint and the schema are unchanged.

## Test plan
pytest, run locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files that Alembic migrates. The tests cover:
- a claimed device now, on each of two made-up customers
- exactly at the start of an assignment, and one second before the first claim
- a moved device: before, at and after the move
- a released device: before the release, at it, and later
- a known device that was never claimed, and an unknown device
- overlapping rows raising, while a time covered by only one row still resolves
- an untimed or non-integer time refused

No bench test is needed, because nothing touches hardware.

## Out of scope
Users, roles and Cognito; per-customer filtering on the readings endpoint; the claim, move and release flow and its transaction; QR codes and certificates; what happens to records from unclaimed or unknown devices (S-073 [Confirm] 2); the audit trail; admin screens; the TimescaleDB container; the queue consumer; the IoT Core rule; the Docker image; Terraform; and the dashboard.

## Open questions [Confirm]
1. **Two calls instead of one optional time.** The request was one helper with an optional time. A `None` time that means "now" would place an untimed scan, whose `unix_time_s` is `None`, on the current tank. Recommended: `owner_now` and `owner_at`, as built.
2. **"Now" is the open assignment**, which is S-073's definition of the current one, not the wall clock. The two differ only if a row starts or ends in the future, which the claim and move story should not write. Recommended: keep it this way, so the answer does not depend on the server's clock.
3. **What the caller does with an overlap.** Recommended for P1-20: treat it as "show nothing", log the device ID, and leave the fix to an admin. The claim and move story should prevent overlap in the first place.
4. **Unknown and unclaimed stay apart**, although both mean that nobody sees the records. That way the later decision on records from devices missing from `devices` (S-073 [Confirm] 2) can treat them differently.

## PR checklist notes
Title `feat(dashboard): resolve a device to its tank, plant and customer (S-074)`, branch `feature/S-074-backend-device-owner`, `Closes #151`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
