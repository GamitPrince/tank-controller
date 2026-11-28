# backend

The Tank-AI cloud backend: a Python FastAPI app (ADR-0008, and ADR-0008 amendment 2 for the folder). Phase 1 is read-only: it will receive and serve plant data and never commands a device.

So far it is a skeleton (S-066) with one endpoint, `GET /health`, which returns `{"status": "ok", "version": "<app version>"}`. The version comes from `pyproject.toml`. Everything runs locally; no cloud account is used (ADR-0007's three gates).

`tankapi.records.decode_message` (S-067) decodes one MQTT message, a CBOR batch of one to five records (`interfaces/records.cddl`), into typed scan and gap records, or raises `DecodeError` naming the record and the reason.

`tankapi.db` maps scan records and their readings (S-068, `migrations/versions/0001_records.py`) and gap records (S-069, `0002_gap_records.py`) to their tables, with check constraints that keep a faulted reading without a value. `tankapi.store.store_message` (S-070) writes the records of one decoded message in one transaction, all or none, and skips a scan whose device, boot ID and sequence are already stored, or a gap identical to a stored one, so a message delivered twice stores nothing new. `tankapi.ingest.ingest_message` (S-071) takes one MQTT message's topic and payload, refuses a topic other than `tank/{device_id}/records`, a payload that does not decode, or a record from another device (nothing written, logged without the payload), and stores the rest with `store_message`. Nothing calls it yet; the queue consumer is a later story. `GET /v1/devices/{device_id}/readings?signal=<id>&from=<t>&to=<t>` (S-072, `tankapi.readings`) returns one signal's stored readings in `[from, to)` (Unix seconds, up to one hour), each with quality and age, plus the gaps that overlap the range; it reads the database named by `TANKAPI_DATABASE_URL`. Every `/v1` request needs a Cognito access token (S-075, `tankapi.auth`). A customer's caller sees only scans taken while the device was on that customer's tanks, no untimed scans (`untimed` is null) and only gaps lying wholly in that time; any other device or time gets the same 404 as an unknown device (S-078). Service, our staff, sees everything, and every service request is recorded in the audit trail (S-080, `tankapi.audit`), refused ones included; the API still runs locally only until the blockers in S-080's spec are done. `tankapi.db` also maps the append-only audit table `audit_entries` (S-079, `0004_audit_entries.py`), whose triggers refuse UPDATE and DELETE. `tankapi.db` also maps who owns each device (S-073, `0003_ownership.py`): customers, plants, tanks, devices, and device-to-tank assignments dated so that a move keeps the old one. `tankapi.ownership` (S-074) reads them: `owner_now` and `owner_at` return a device's customer, plant and tank, now or at a scan's time, or say it is unclaimed at that time or unknown, and raise if assignments overlap. `customer_windows` (S-077) gives the stretches of time in which a device was on one customer's tanks within a range, with the same answer as `owner_at` for every second, and refuses a device whose assignments overlap anywhere. Nothing writes them yet; the readings endpoint calls `customer_windows`. `tankapi.level.compute_level` (S-082) turns one radar reading (signal 1001) into a level height, level % and volume from a tank's transducer range and strapping table, or gives an explicit `fault`, `out_of_range` or `stale` status with no figures; every result carries the table version and the calculation version. Nothing calls it yet and no table is stored yet. `tankapi.liveness` (S-083) says whether a stored reading is `live`, `stale` or `time-unknown` against the server clock, with thresholds from `TANKAPI_STALE_ALLOWANCE_S`, `TANKAPI_STALE_AGE_FACTOR` and `TANKAPI_CLOCK_AHEAD_S` (defaults in the module). `GET /v1/devices/{device_id}/latest` (S-084, `tankapi.latest`) returns each signal's newest value with its `liveness`, and the device's own state, for a live view; a customer sees it only while the device is on one of their tanks. `tankapi.db` also maps each tank's level configuration with its history (S-085, `0005_level_configurations.py`): transducer range, full height and strapping points, whose rows the database refuses unless each rises over the one before. `tankapi.level_config.level_config_at` (S-086) returns the configuration in force at a given time, and `/latest` returns `level`: level % and volume computed on read from the newest radar reading with the configuration of the tank the device was on then, or a status saying why there are none (`tankapi.tank_level`). Nothing writes the configuration outside the tests yet. `tankapi.db` also maps each tank's advisory alarm thresholds with their history (S-087, `0006_alarm_thresholds.py`), refusing one on a device contact. `tankapi.alarm_rules.evaluate` (S-088) judges one reading or level % against one threshold: normal, high, low, or `cannot_evaluate` for a fault, stale, untimed or missing value. `alarm_events` (S-089, `0007_alarm_events.py`) is the append-only alarm history, one row per change of state, and `tankapi.thresholds.thresholds_at` gives a tank's thresholds at a scan's time. Ingest records them (S-090, `tankapi.alarm_events`): each new scan is judged against the thresholds in force at its own time, in the ingest transaction, and a row is added only when an alarm's state changes. `GET /v1/tanks/{tank_id}/alarms` (S-091, `tankapi.alarm_history`) reads a tank's events back, newest first, to the tank's own customer and to service. `alarm_acknowledgements` (S-092, `0008_alarm_acknowledgements.py`) is the append-only record of who acknowledged a raised event and when, at most once. `POST /v1/alarms/{event_id}/acknowledgement` (S-093, `tankapi.alarm_acknowledge`) writes it for a customer's operator, maintenance or admin, for a raise still in force; it changes nothing about the alarm. The history shows each event's acknowledgement, or null (S-094). `config_changes` (S-101, `0010_config_changes.py`) is the append-only log of every change to a tank's alarm thresholds or level configuration: who, role (admin or service), server time, tank, and the values before and after as JSON. `PUT /v1/tanks/{tank_id}/alarm-thresholds` (S-102, `tankapi.threshold_edit`) sets one alarm's threshold for the tank's own admin or for service: the row in force is closed at the server's second and the new one holds from it, so an older scan is still judged by the old limit, and the change goes in `config_changes` in the same transaction. Operator and maintenance get 403. Nothing in the backend writes to a device. Create the tables in a local database from `backend/` (the URL is never written in the repository):

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

### Also on PostgreSQL (S-098)

Tests marked `postgres` (the migrations, the stored records, ingest, the audit trail and the alarm tables) run on SQLite and also on a PostgreSQL server when `TANKAPI_TEST_DATABASE_URL` is set; without it their Postgres runs are skipped, which is how CI runs today. `tests/test_postgres.py` adds what only a server shows: TRUNCATE refused on the three append-only tables, and the backend role's rights. Each Postgres test creates a database named `tankai_test`, migrates it and drops it afterwards. If a database of that name already exists the test fails instead of using or dropping it. Tests cannot run in parallel against one server.

One-time setup, done by hand by the database administrator as `postgres` (choose the password yourself; it is never written in the repository or in chat):

```sql
CREATE ROLE tankai_dev LOGIN CREATEDB PASSWORD '<choose one>';
CREATE ROLE tankapi_backend NOLOGIN;
GRANT tankapi_backend TO tankai_dev;
```

Put the password in libpq's password file, `%APPDATA%\postgresql\pgpass.conf` on Windows or `~/.pgpass` (mode 0600) on Ubuntu, as one line: `localhost:5432:*:tankai_dev:<the same password>`. Then run the tests with a URL that carries no password:

```bash
TANKAPI_TEST_DATABASE_URL="postgresql+psycopg://tankai_dev@localhost:5432/postgres" PYTHON=python bash scripts/ci/run-component.sh backend
```

The backend role may only add and read audit entries. `sql/backend-role-grants.sql` gives it that: SELECT and INSERT on `audit_entries` and use of its sequence, and nothing else. Run it as the table owner after `alembic upgrade head`; the tests run it the same way. The role does not own the table, so it cannot drop the append-only triggers.

### TimescaleDB (S-100)

Migration 0009 adds `reading_samples`, one row per reading of a time-known scan at the scan's time `t`. On PostgreSQL where TimescaleDB is available it runs `CREATE EXTENSION IF NOT EXISTS timescaledb` (the extension is trusted, so the database owner needs no superuser rights) and makes the table a hypertable with one-day chunks and a 90-day retention policy; the `reading_minutes` continuous aggregate summarises each device, signal and minute over good samples only and is kept forever. On SQLite, or a PostgreSQL without TimescaleDB, the table stays plain and nothing is dropped (the migration logs a warning on PostgreSQL). `scan_records`, `readings` and `gap_records` are never trimmed: until the raw archive exists they stand in for it. The tests set `timescaledb.telemetry_level` to `off` on each throwaway database; the server-wide setting is the administrator's. `tests/test_reading_samples.py` holds the TimescaleDB tests, run only on the server.

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
