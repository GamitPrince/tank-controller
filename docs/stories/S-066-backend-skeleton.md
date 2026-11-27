# S-066: Add the backend skeleton

- Story ID: S-066 (issue #135).
- Epic: E4 (groundwork for P1-17). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author; **this story edits `.github/workflows/ci.yml`**, so that approval must come from a `.github/` code owner other than the author. Not a safety path.

## Goal
The backend has a home, a toolchain and a CI job before any feature lands in it: a FastAPI app with one health endpoint, tested, linted and held to the 80% gate like every other component.

## Phase check
Phase 1. No plant data, no device contact, no cloud account and no AWS resource: everything runs locally (ADR-0007's three gates still hold). The app only reports that it is up.

## Decisions already made
- **ADR-0008 decision 1:** Python with FastAPI. **Decision 6:** pytest with its coverage plugin, a `ci.sh` that writes a Cobertura `coverage.xml`, the 80% gate counting all our code. **Decision 7:** REST with OpenAPI, versioned.
- **ADR-0008 amendment 2 (26 Nov 2026):** the backend lives in the repository-root `backend/` folder, apart from `dashboard/`.
- **CHORE-01 / `scripts/ci/run-component.sh`:** the component contract. `backend/ci.sh` copies `simulator/ci.sh`.

## Files to create or change
- `backend/pyproject.toml`, `backend/requirements-dev.txt` (pinned FastAPI, uvicorn, pytest, pytest-cov, httpx2, ruff).
- `backend/tankapi/main.py`: the app and `GET /health`. `backend/tests/test_health.py`.
- `backend/ci.sh`, `backend/README.md`.
- **`.github/workflows/ci.yml`** (explicitly in scope, AGENTS.md section 11): a `backend` output of the `changes` job for `^backend/`, which also turns on for the shared paths like every other component; a `backend` job that runs `bash scripts/ci/run-component.sh backend`; `backend` in `ci-gate`'s needs.
- `docs/stories/README.md`, `CHANGELOG.md`.
- `.gitignore`: no change. `.venv/` and `coverage.xml` are already ignored at every depth.

## Interfaces touched
None. `interfaces/` is not read yet; CBOR decoding is a later story.

## Acceptance criteria
- `GET /health` returns 200 and `{"status": "ok", "version": "<version>"}`, the version read from the installed package metadata so `pyproject.toml` is the only place it is written.
- `POST /health` is refused (405), an unknown path is 404, and the OpenAPI document lists `/health` alone, with the app version.
- `bash scripts/ci/run-component.sh backend` creates the venv, passes ruff check and ruff format, runs pytest, writes `backend/coverage.xml`, and clears 80%.
- A pull request touching `backend/` runs the `backend` job, and `ci-gate` fails if it fails.

## Test plan
pytest with FastAPI's `TestClient`, run locally on Windows (Git Bash, `PYTHON=python`) and in GitHub CI on Ubuntu. No bench test: nothing touches hardware.

## Out of scope
The database and Alembic, a local TimescaleDB container, CBOR decoding of the batch message, MQTT or IoT Core ingest, Cognito login, the Docker image, Terraform, the dashboard. One story each, later.

## Open questions [Confirm]
1. **PR title scope:** `pr-policy` has no `backend` scope and must not be edited, so the title uses `dashboard`, because ADR-0008 treats backend and dashboard as one component (recommended, taken). A `backend` scope would be a `pr-policy` change of its own.
2. **`httpx2` instead of `httpx`:** Starlette 1.10, which FastAPI 0.165 installs, deprecates `httpx` for its `TestClient`, and with `filterwarnings = error` the tests fail. Its extras also cap `httpx` below 0.29. `httpx2` (Pydantic's successor to `httpx`, the one Starlette names) is pinned instead (recommended, taken). Silencing the warning was the alternative.
3. **`/health` is unversioned:** it is an operational probe for the container platform, not part of the versioned REST API of decision 7, which starts under a version prefix with the first data endpoint (recommended, taken).

## PR checklist notes
Title `feat(dashboard): add the backend skeleton (S-066)`, branch `feature/S-066-backend-skeleton`, `Closes #135`. No `safety` label. No screenshots: there is no screen.
