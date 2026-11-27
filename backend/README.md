# backend

The Tank-AI cloud backend: a Python FastAPI app (ADR-0008, and ADR-0008 amendment 2 for the folder). Phase 1 is read-only: it will receive and serve plant data and never commands a device.

So far it is a skeleton (S-066) with one endpoint, `GET /health`, which returns `{"status": "ok", "version": "<app version>"}`. The version comes from `pyproject.toml`. Everything runs locally; no cloud account is used (ADR-0007's three gates).

`tankapi.records.decode_message` (S-067) decodes one MQTT message, a CBOR batch of one to five records (`interfaces/records.cddl`), into typed scan and gap records, or raises `DecodeError` naming the record and the reason.

`tankapi.db` maps scan records and their readings (S-068, `migrations/versions/0001_records.py`) and gap records (S-069, `0002_gap_records.py`) to their tables, with check constraints that keep a faulted reading without a value. `tankapi.store.store_message` (S-070) writes the records of one decoded message in one transaction, all or none, and skips a scan whose device, boot ID and sequence are already stored, or a gap identical to a stored one, so a message delivered twice stores nothing new. `tankapi.ingest.ingest_message` (S-071) takes one MQTT message's topic and payload, refuses a topic other than `tank/{device_id}/records`, a payload that does not decode, or a record from another device (nothing written, logged without the payload), and stores the rest with `store_message`. Nothing calls it yet; the queue consumer is a later story. `GET /v1/devices/{device_id}/readings?signal=<id>&from=<t>&to=<t>` (S-072, `tankapi.readings`) returns one signal's stored readings in `[from, to)` (Unix seconds, up to one hour), each with quality and age, plus the gaps that overlap the range; it reads the database named by `TANKAPI_DATABASE_URL`. Every `/v1` request needs a Cognito access token (S-075, `tankapi.auth`). A customer's caller sees only scans taken while the device was on that customer's tanks, no untimed scans (`untimed` is null) and only gaps lying wholly in that time; any other device or time gets the same 404 as an unknown device (S-078). Service, our staff, sees everything, and every service request is recorded in the audit trail (S-080, `tankapi.audit`), refused ones included; the API still runs locally only until the blockers in S-080's spec are done. `tankapi.db` also maps the append-only audit table `audit_entries` (S-079, `0004_audit_entries.py`), whose triggers refuse UPDATE and DELETE. `tankapi.db` also maps who owns each device (S-073, `0003_ownership.py`): customers, plants, tanks, devices, and device-to-tank assignments dated so that a move keeps the old one. `tankapi.ownership` (S-074) reads them: `owner_now` and `owner_at` return a device's customer, plant and tank, now or at a scan's time, or say it is unclaimed at that time or unknown, and raise if assignments overlap. `customer_windows` (S-077) gives the stretches of time in which a device was on one customer's tanks within a range, with the same answer as `owner_at` for every second, and refuses a device whose assignments overlap anywhere. Nothing writes them yet; the readings endpoint calls `customer_windows`. `tankapi.level.compute_level` (S-082) turns one radar reading (signal 1001) into a level height, level % and volume from a tank's transducer range and strapping table, or gives an explicit `fault`, `out_of_range` or `stale` status with no figures; every result carries the table version and the calculation version. Nothing calls it yet and no table is stored yet. `tankapi.liveness` (S-083) says whether a stored reading is `live`, `stale` or `time-unknown` against the server clock, with thresholds from `TANKAPI_STALE_ALLOWANCE_S`, `TANKAPI_STALE_AGE_FACTOR` and `TANKAPI_CLOCK_AHEAD_S` (defaults in the module). `GET /v1/devices/{device_id}/latest` (S-084, `tankapi.latest`) returns each signal's newest value with its `liveness`, and the device's own state, for a live view; a customer sees it only while the device is on one of their tanks. Create the tables in a local database from `backend/` (the URL is never written in the repository):

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

The token check (S-075) reads three environment settings, none of them written in the repository: `TANKAPI_AUTH_ISSUER` (the user pool's issuer URL), `TANKAPI_AUTH_CLIENT_ID` (its app client), and exactly one of `TANKAPI_AUTH_JWKS_FILE` (a local JWKS file) or `TANKAPI_AUTH_JWKS_URL` (the pool's JWKS, HTTPS only). Without them every `/v1` request gets 503; `/health` needs no token. A valid token must also name exactly one role in `cognito:groups` (`operator`, `maintenance`, `admin` or `service`) and, except for `service`, a customer in `custom:customer_id` (S-076); otherwise the request gets 403.

Then open <http://127.0.0.1:8000/health>, or <http://127.0.0.1:8000/docs> for the OpenAPI page. Uvicorn binds to `127.0.0.1` by default, so the app is not reachable from other machines.

The app must be installed (the tests do `pip install -e .`), because it reads its version from the package metadata.
