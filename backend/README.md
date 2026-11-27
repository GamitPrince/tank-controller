# backend

The Tank-AI cloud backend: a Python FastAPI app (ADR-0008, and ADR-0008 amendment 2 for the folder). Phase 1 is read-only: it will receive and serve plant data and never commands a device.

So far it is a skeleton (S-066) with one endpoint, `GET /health`, which returns `{"status": "ok", "version": "<app version>"}`. The version comes from `pyproject.toml`. Everything runs locally; no cloud account is used (ADR-0007's three gates).

`tankapi.records.decode_message` (S-067) decodes one MQTT message, a CBOR batch of one to five records (`interfaces/records.cddl`), into typed scan and gap records, or raises `DecodeError` naming the record and the reason. Nothing is stored yet.

`tankapi.db` (S-068) maps scan records and their readings to the tables that `migrations/versions/0001_records.py` creates, with check constraints that keep a faulted reading without a value. Nothing writes to them yet. Create the tables in a local database from `backend/` (the URL is never written in the repository):

```bash
TANKAPI_DATABASE_URL="sqlite:///$TEMP/tankapi.db" .venv/Scripts/python.exe -m alembic upgrade head
```

## Run the tests

The same way CI does, from the repository root. It creates `backend/.venv`, installs the pinned `requirements-dev.txt`, runs the ruff lint and format checks, runs pytest, and writes `backend/coverage.xml`; the 80% line-coverage gate applies.

Windows (Git Bash; `python3` is often a Microsoft Store stub, so name the interpreter):

```bash
PYTHON=python bash scripts/ci/run-component.sh backend
```

Ubuntu:

```bash
bash scripts/ci/run-component.sh backend
```

## Run the app

After the tests have created the venv, from `backend/`:

Windows (Git Bash):

```bash
.venv/Scripts/python.exe -m uvicorn tankapi.main:app --reload
```

Ubuntu:

```bash
.venv/bin/python -m uvicorn tankapi.main:app --reload
```

Then open <http://127.0.0.1:8000/health>, or <http://127.0.0.1:8000/docs> for the OpenAPI page. Uvicorn binds to `127.0.0.1` by default, so the app is not reachable from other machines.

The app must be installed (the tests do `pip install -e .`), because it reads its version from the package metadata.
