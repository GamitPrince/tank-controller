# S-076: Read the caller's role and customer from the token

- Story ID: S-076 (issue #155).
- Epic: E4 (groundwork for P1-20). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched.

## Goal
Once S-075's token check passes, the backend knows the caller's role and customer, read from the access token, and every `/v1` handler can take them. A valid token that names no usable role or customer is refused before any plant data is read.

## Phase check
Phase 1, read-only. The change only refuses requests: nothing is written and no device is contacted. No Cognito user pool, no AWS resource and no account (ADR-0007's three gates still hold). Tests generate their RSA keys at run time and make no network call.

## Decisions already made
- **ADR-0008 decision 3:** a user belongs to exactly one customer; the roles are operator, maintenance, admin (the customer's) and service (our staff, audited); the customer ID and role travel in the login token and the backend checks them on every request.
- **S-075 [Confirm] 1 to 5, confirmed by the tech lead on 27 Nov 2026:** the access token, not the ID token; no per-customer scoping yet, so the API stays local only; 503 while unconfigured; 30 s leeway, keys cached for one hour, a failed key fetch is 401; role and customer split out to this story.
- **Confirmed by the tech lead on 27 Nov 2026:**
  1. The role comes from `cognito:groups`, which must hold **exactly one** of `operator`, `maintenance`, `admin` or `service`. No role, or two of them, gives 403. Any other group name is ignored.
  2. The customer is **`custom:customer_id`**: our `customers.id` as plain decimal digits in a string. Missing or malformed gives 403; a decimal string that is not a positive integer counts as malformed.
  3. A **service** caller is never tied to a customer. A service token without the claim is allowed; any customer value on it is ignored and recorded as none. **Service access is audited by S-080:** every `/v1` request by a service caller is recorded in the append-only audit table.

## Files to create or change
- `backend/tankapi/auth.py`: `Role`, `Caller.role` and `Caller.customer_id`, `caller_from`, and the 403 in `require_caller`.
- `backend/tests/test_auth.py`, `backend/tests/access_tokens.py` (the default token is an operator of customer 7), `backend/tests/test_readings.py`.
- `backend/README.md`, `docs/stories/S-075-backend-token-check.md` (its `[Confirm]` lines only), `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` is not changed, and the OpenAPI document is unchanged: the 403 is not declared on the operation ([Confirm] 3).

## Acceptance criteria
- `require_caller` returns `Caller(subject, role, customer_id)`: `role` is a `Role`, `customer_id` an integer, or `None` for service only.
- The role and customer are checked only after the token passes, so a bad token is still 401 whatever its claims.
- No role, two roles, or a groups claim that is not a list gives 403. Group names that are not roles, and entries that are not strings, are ignored.
- For operator, maintenance and admin, `custom:customer_id` must be a string matching `[1-9][0-9]{0,17}` (a positive integer that fits a BIGINT, no sign, padding, spaces, decimal point or non-ASCII digits); otherwise 403.
- Every 403 has the body `{"detail": "not allowed"}` and no `WWW-Authenticate` header. The reason is logged with the caller's `sub`; the token and the claim values never are.
- All four roles may read `GET /v1/devices/{device_id}/readings`.
- A handler takes the caller with `Depends(require_caller)`; FastAPI runs the check once per request.

## Test plan
pytest with FastAPI's `TestClient`, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. Cases: each of the four roles with customer 7 (service comes back with none); service with no, a malformed or a zero customer (none); a role among unrelated and non-string groups, with an 18-digit customer; and 403 for no groups claim, empty groups, groups not a list, two roles, an unknown group alone, and a missing, empty, non-digit, zero, negative, zero-padded, space-padded, float-like, numeric, 19-digit or Arabic-Indic customer, each checking the fixed body, no `WWW-Authenticate`, the logged reason and that the token is not in the log. A bad signature with no groups is still 401. Each role reads the readings endpoint (200). No bench test: nothing touches hardware.

## Out of scope
Per-customer, per-plant and per-tank scoping of the readings endpoint (a later story, using S-074's owner helper); per-role permissions; the audit trail, including service access; the Cognito user pool, its groups, its pre-token-generation trigger and Terraform; sign-in screens; users stored in our database; plant or tank limits in the token; the Docker image; the dashboard.

## Open questions [Confirm]
1. **The customer is not looked up in the database here** (recommended, taken). A customer ID that matches no `customers` row passes this check; the scoping story refuses it when it resolves the device's owner, so this story adds no database read to every request.
2. **A 403 is logged at warning level with the caller's `sub`** (recommended, taken). A token our own pool signed but without a usable role or customer points at a user set up wrongly, so it is worth seeing; `sub` is Cognito's opaque user ID, not the token, and the reason text never contains claim values.
3. **The 403 is not declared in the OpenAPI document yet** (recommended, taken). The 401 and 503 are not declared either; documenting the error responses together is left to the dashboard's generated types (ADR-0008 decision 1).

## PR checklist notes
Title `feat(dashboard): read the caller's role and customer from the token (S-076)`, branch `feature/S-076-backend-role-customer`, `Closes #155`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. No migration and no new dependency.
