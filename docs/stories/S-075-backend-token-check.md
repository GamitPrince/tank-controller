# S-075: Check a Cognito-style token on every /v1 request

- Story ID: S-075 (issue #153).
- Epic: E4 (groundwork for P1-20). Points: 3. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched.

## Goal
No `/v1` request reaches a handler without a valid Amazon Cognito access token. The backend checks the token itself, on every request, before it reads any plant data, and tells the handler who the caller is.

## Phase check
Phase 1, read-only. The check only refuses requests: nothing is written and no device is contacted. No Cognito user pool, no AWS resource and no account (ADR-0007's three gates still hold). Tests generate their RSA keys at run time and make no network call.

## Decisions already made
- **ADR-0008 decision 2:** login is Amazon Cognito Essentials. **Decision 3:** the backend checks every request and never trusts the browser. **Decision 7:** REST under `/v1`, described by OpenAPI.
- **ADR-0005 rule 9:** no key, token or secret in the public repository, so the pool's issuer, app client ID and key location are environment settings.
- **S-066, S-072:** `/health` is an operational probe outside `/v1`; the readings endpoint is the first `/v1` route.

## Files to create or change
- `backend/tankapi/auth.py`: `require_caller`, the settings, and the two key sources behind one `KeySource` interface: `JwksKeys` (a JWKS already in memory, from a local file or a test) and `RemoteJwks` (the pool's JWKS over HTTPS, cached).
- `backend/tankapi/main.py`: one `/v1` router with `require_caller` as its dependency; `backend/tankapi/readings.py` loses its own `/v1` prefix.
- `backend/tests/test_auth.py`, `backend/tests/access_tokens.py` (test keys and tokens); `backend/tests/test_readings.py` sends a token.
- `backend/pyproject.toml`, `backend/requirements-dev.txt`: PyJWT with its crypto extra, and cryptography.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` is not changed.

## Acceptance criteria
- Every `/v1` route requires `Authorization: Bearer <token>`. `/health` needs no token.
- A token is accepted only when its header names `RS256` and a `kid` in the configured JWKS, its signature verifies with that key, `iss` is the configured issuer, `exp` has not passed and `nbf` (when present) has, `client_id` is the configured app client, `token_use` is `access`, and `sub` is a non-empty string. `none`, HS256 (including one signed with the public key as the secret) and every other algorithm are refused; a symmetric key in the JWKS is never used.
- A missing, malformed or refused token gets 401 with `WWW-Authenticate: Bearer` and the same body every time, `{"detail": "not authenticated"}`. The reason is logged; the token never is.
- Settings: `TANKAPI_AUTH_ISSUER`, `TANKAPI_AUTH_CLIENT_ID`, and exactly one of `TANKAPI_AUTH_JWKS_FILE` or `TANKAPI_AUTH_JWKS_URL` (HTTPS only). Anything else is unconfigured, and then every `/v1` request gets 503.
- The handler can take the caller's identity (`sub`) from `require_caller`.
- OpenAPI declares the `HTTPBearer` scheme on every `/v1` operation and not on `/health`.

## Test plan
pytest with FastAPI's `TestClient`, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. Each test signs its tokens with an RSA key generated at run time and passes the matching JWKS in through the settings. Cases: a valid token names its caller; an expired, not-yet-valid, wrong-issuer, other-client, ID-shaped, wrong-`token_use`, no-expiry, no-subject and empty-subject token; a bad signature; an unknown `kid`; `alg: none`; HS256 signed with the public key; a malformed token; a missing header, a Basic header and an empty Bearer header; the unconfigured app (503, `/health` still 200); a symmetric key in the JWKS; five incomplete settings; a local JWKS file; a JWKS URL fetched through a stubbed fetch, with an unknown `kid` refused; the OpenAPI security scheme. The S-072 tests now send a valid token. No bench test: nothing touches hardware.

## Out of scope
The caller's role and customer (S-076, below); per-customer, per-plant and per-tank scoping of the readings endpoint (a later story, using S-074's owner helper); the Cognito user pool, its app client and its Terraform; the pre-token-generation trigger; sign-in screens and the hosted UI; refresh tokens; users stored in our database; the audit trail; rate limiting; the Docker image; the dashboard.

## Open questions [Confirm]
1. **The access token, not the ID token** (recommended, taken; **confirmed by the tech lead, 27 Nov 2026**). The access token is the one meant for an API: Cognito marks it `token_use: access` and names the app client in `client_id`, and scopes can be added later. The ID token is meant for the browser to learn who signed in; its `aud` is the app client. The cost: our customer claim reaches the access token only through Cognito's pre-token-generation trigger (V2 event, included in Essentials; it is ADR-0008 decision 2's "our own values in the login token"), a small Lambda for the user-pool story. `cognito:groups` is in both tokens. Switching to the ID token means checking `aud` and `token_use: id` instead: a few lines.
2. **No per-customer scoping yet** (**confirmed by the tech lead, 27 Nov 2026**). Until the scoping story lands, any valid token reads any device. The API stays local-only and must not be deployed before that story.
3. **Unconfigured is 503, not 401** (**confirmed by the tech lead, 27 Nov 2026**). A missing setting is the server's fault, not the caller's; the app still fails closed.
4. **30 s clock leeway** on `exp` and `nbf` (**confirmed by the tech lead, 27 Nov 2026**, with the key caching and the 401 below). **Pool keys are cached for one hour**, and an unknown `kid` makes PyJWT fetch the JWKS again. A failed fetch counts as an unknown key (401, logged), not 503.
5. **Split for size** (**confirmed by the tech lead, 27 Nov 2026**; the role and customer rules are decided in S-076's spec). The brief also asked for the role from `cognito:groups` (exactly one of operator, maintenance, admin, service; none or two gives 403) and the customer from a claim (proposed `custom:customer_id`, our `customers.id` as decimal digits; missing gives 403 except for `service`). That is the next story, S-076, so this PR stays reviewable. The audit trail for the service role is a later story again.

## PR checklist notes
Title `feat(dashboard): check a Cognito-style token on every /v1 request (S-075)`, branch `feature/S-075-backend-token-check`, `Closes #153`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. PyJWT 2.15.1 and cryptography 50.0.2 were the latest releases on 27 Nov 2026; every GitHub advisory for each package (24 each, queried with `gh api graphql`) was checked against those versions, and none covers them.
