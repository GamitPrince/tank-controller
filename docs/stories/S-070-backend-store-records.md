# S-070: Store decoded records in the backend database

- Story ID: S-070 (issue #143).
- Epic: E4 (groundwork for P1-17). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend can write the records of one decoded MQTT message into its database, all of them or none, and a message delivered twice stores nothing the second time. MQTT QoS 1 delivers at least once, and the FRDM replays its backlog after an outage, so duplicates are normal traffic, not errors.

## Phase check
Phase 1, read-only. A function that writes to the backend's own database: no broker, no endpoint, no command to any device, no cloud account and no AWS resource (ADR-0007's three gates still hold). Tests run on local SQLite files.

## Decisions already made
- **ADR-0004 decisions 5, 7 and 8:** sequence numbers and delivery confirmation on the device link; MQTT QoS 1 (at least once); failover and backlog replay, oldest first, with original timestamps.
- **ADR-0007 / ADR-0008:** the backend stores the records; level %, volume and summaries are computed later, in the cloud.
- **P1-17:** forwarded backlog creates no duplicates; de-duplication is by boot ID and sequence number.
- **S-040:** a gap record marks dropped scans; two gaps' ranges may overlap, but every dropped scan is counted in exactly one gap; nothing interpolates across a gap.
- **S-067 / S-068 / S-069:** `decode_message` returns typed records; `scan_records` has a unique `(device_id, boot_id, sequence)`; `gap_records` has no unique key.

## Files to create or change
- `backend/tankapi/store.py`: `store_message(session, records) -> StoreResult` (`stored`, `skipped`).
- `backend/tests/test_store.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

No migration: the scan key exists (S-068), and gaps are de-duplicated in code ([Confirm] 1).

## Interfaces touched
None changed. `interfaces/` is not read or written.

## Acceptance criteria
- `store_message` writes every record of one message in one transaction, which it begins and commits; if any write fails, it rolls back, nothing of the message is stored, and the error is raised.
- A scan record whose device, boot ID and sequence are already stored, or already earlier in the same message, is skipped: not overwritten, not an error. The result counts stored and skipped records.
- A gap record identical in every field to a stored one is skipped ([Confirm] 1).
- Exactly what was decoded is stored: the device's `up`, `tk` and `t`, never the arrival time; quality and age on every reading; no value for a faulted or unconfigured reading; nothing is added between or across records.

## Test plan
pytest, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files migrated by Alembic:
- the simulator batch fixture stored and read back field for field, value types included;
- the same message twice: everything skipped the second time, nothing changed;
- a batch overlapping a stored one: only the new scans stored;
- a duplicate inside one message;
- a gap record stored, redelivered (skipped), and a different gap with the same `first` stored;
- a failure part-way through a message: nothing written, and the database still usable.

No bench test: nothing touches hardware.

## Out of scope
The TimescaleDB container, hypertables and retention; MQTT or IoT Core ingest; the managed queue; a dead-letter path for refused messages; comparing `dev` with the topic's device ID; the customer > plant > tank > device tables and the claim flow; HTTP endpoints for records; per-minute summaries; level % and volume; Cognito; the Docker image; Terraform; the dashboard.

## Open questions [Confirm]
1. **Gap de-duplication by the whole record, in code, with no migration** (recommended, taken). Every dropped scan is counted in exactly one gap (S-040), so two genuinely different gaps cannot agree in device, `lost` and both marks; an identical one is a redelivery. A gap carried forward keeps its `first` but has a different `last` or `lost`, so it is stored. A unique key over eleven columns, two of them nullable, would not even catch the NULL case in Postgres, so the check is a lookup.
2. **Look up, then insert** (recommended, taken), rather than dialect-specific `ON CONFLICT DO NOTHING`, so the same code runs on SQLite and Postgres. With one consumer this is exact. Two consumers storing the same scan at once would make the second hit the unique key and roll back its whole message, which QoS 1 redelivers and the retry then skips; two racing copies of a gap could both be stored. Concurrent consumers are for the ingest story to settle.
3. **The function owns the transaction**: it takes a session with no transaction open, so "all or none" holds without trusting the caller.

## PR checklist notes
Title `feat(dashboard): store decoded records in the backend database (S-070)`, branch `feature/S-070-backend-store-records`, `Closes #143`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
