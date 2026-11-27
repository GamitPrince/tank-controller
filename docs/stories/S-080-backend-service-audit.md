# S-080: Audit service-staff access in the backend

- Story ID: S-080 (issue #162).
- Epic: E4 (P1-20). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched; no new dependency. Built on S-079 (#161), the audit table, which merges first; split from it for PR size.

## Goal
Every `/v1` request a **service** caller (our staff) makes is recorded in S-079's append-only audit table, so nothing our staff read of a customer's data goes unrecorded (ADR-0008 decisions 3 and 4, P1-20). S-076 decision 3 and S-078 [Confirm] 5 left service access unaudited, which was the stated reason the API must stay local-only.

## Phase check
Phase 1, read-only for plant data. The audit entry is the backend's own record: nothing is sent to a device and no endpoint reads or edits the table. No S3 bucket, no AWS resource, no account (ADR-0007's three gates still hold). Tests generate their keys at run time, make no network call, and every name in them is made up.

## Decisions already made
- **ADR-0008 decision 3:** service may support any customer, and every such access is recorded in the audit trail. **Decision 4:** an append-only table the backend can add to but not edit or delete, plus a daily write-once S3 copy (Object Lock).
- **S-079:** the table `audit_entries` and its columns; triggers refuse UPDATE and DELETE.
- **S-076:** the role comes from `cognito:groups`; a service caller has no customer. **S-078:** service is never limited.

## Files to create or change
- `backend/tankapi/audit.py` (new), `backend/tankapi/main.py`; docstrings only in `auth.py`, `db.py` and `readings.py`.
- `backend/tests/test_audit.py` (new).
- `backend/README.md`, `docs/stories/S-075-*.md`, `S-076-*.md` and `S-078-*.md` (only their lines saying service access is unaudited), `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
`interfaces/` is not changed. The OpenAPI document is unchanged; a service request may now get 503 `{"detail": "not available"}` ([Confirm] 1).

## Acceptance criteria
- One `audit_entries` row per request: `at_unix_ms` (server time of the request), `subject` (`sub`), `role`, `method`, `route` (template, for example `/v1/devices/{device_id}/readings`), `device_id` (as sent, cut to 64 characters, null if the route has none), `query` (JSON of the selecting parameters `signal`, `from` and `to` as sent, each cut to 64 characters) and `status`. Never the token, the Authorization header, any other header or query parameter, or a reading.
- Every `/v1` request by a caller identified as service writes one entry with the response's status, refused ones included (404, 422 from the handler or from FastAPI, 500). A request refused before the caller is known (401, 403, 503) writes none.
- A failed audit write gives 503 instead of the response, logged at error level with the `sub` and the route, never the token ([Confirm] 1).
- Customer callers are not recorded ([Confirm] 2).

## Test plan
pytest with FastAPI's `TestClient` on SQLite files migrated by Alembic, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. A service read is recorded with every field; a 404, a handler 422, a FastAPI 422 and an over-long device ID and value (cut) are recorded; a server error is recorded as 500; operator, maintenance and admin are not recorded; 401 and 403 write nothing; no entry holds the token, its signature, `Bearer`, another header or an unlisted parameter; with no audit table (database at 0003) a service read gets 503 and the log names the caller but not the token. UPDATE and DELETE refusal and the migration are S-079's tests. No bench test: nothing touches hardware.

## Out of scope
The table, its triggers and its migration (S-079); the daily write-once S3 copy with Object Lock, its schedule and its restore-and-verify test (the next audit story; it needs AWS and ADR-0007's gates); any audit read endpoint or screen; auditing admin write actions (none exist yet) and the other ADR-0008 events (logins, claims, settings); the hash chain (Phase 2); retention; the Cognito user pool; per-plant and per-tank limits; the database roles and grants; the Docker image; Terraform; the dashboard.

## Still blocking deployment
1. The daily S3 Object Lock copy of the trail (ADR-0008 decision 4).
2. The Cognito user pool, its groups and its pre-token-generation trigger (S-075 [Confirm] 1, S-076).
3. S-079's Postgres triggers run against a real server, and a backend database role with INSERT and SELECT only on `audit_entries` (the TimescaleDB container story).
4. ADR-0007's three gates: written customer hosting confirmation, the early IoT Core test, the Tiger Cloud check.

## Open questions [Confirm]
1. **Fail closed** (recommended, taken): if the entry cannot be written, the response is dropped and the caller gets 503 `{"detail": "not available"}`, so no service read is ever unrecorded. The handler has already run, but it only reads. The cost: a broken audit table stops our staff, not customers.
2. **Customer callers are not audited** (recommended, taken): ADR-0008 asks only for service, and a customer's dashboard polls all day into a table nothing may delete. A later story can add them.
3. **The entry is written after the response is built**, in its own transaction, not in the handler's: the readings endpoint changes nothing, so there is no change to write it with. Write actions (ADR-0008 decision 4) must write their entry in the same transaction as the change.
4. **Only `signal`, `from` and `to` are recorded** (recommended, taken). Any other query parameter could hold anything, a token included; a new endpoint adds its own selecting names to `SELECTING_PARAMETERS`.

## PR checklist notes
Title `feat(dashboard): audit service-staff access in the backend (S-080)`, branch `feature/S-080-backend-service-audit`, `Closes #162`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. No migration and no new dependency. Built on S-079 (#161): its commit is in this branch until #161 merges.
