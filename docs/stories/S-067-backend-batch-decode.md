# S-067: Decode the CBOR batch message in the backend

- Story ID: S-067 (issue #137).
- Epic: E4 (groundwork for P1-17). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend can turn the bytes of one MQTT message into typed scan and gap records, oldest first, keeping every quality flag and age. It refuses anything the record schema does not allow, with a reason, before any storage or ingest story builds on it.

## Phase check
Phase 1, read-only. A pure function: no I/O, no database, no broker, no cloud account (ADR-0007's three gates still hold). Nothing is sent to a device.

## Decisions already made
- **ADR-0004 decision 6:** CBOR records described by `interfaces/records.cddl`. **S-062:** a message is a batch, `[1*5 message]`, oldest first, each record complete with `v` and `dev`. **S-040:** the gap record. **S-064:** the ESP32 publishes each batch as one MQTT message.
- **ADR-0008:** every value carries a quality flag and an age. **AGENTS.md section 7:** a failed sensor is flagged and excluded, never silently replaced.
- **ADR-0007 decision 6:** the backend decodes CBOR. **S-028:** cbor2 stays on 5.9.0; firmware, simulator and backend move together.

## Files to create or change
- `backend/tankapi/records.py`: `decode_message(payload)` returns a tuple of `ScanRecord` and `GapRecord` (with `Reading`, `LostScan` and `Quality`), or raises `DecodeError` with the record index and the reason.
- `backend/tests/test_records.py`, `backend/tests/test_records_schema.py`, `backend/tests/fixtures/simulator-batch-cbor-hex.txt`.
- `backend/pyproject.toml` (`cbor2>=5.6,<6`), `backend/requirements-dev.txt` (`cbor2==5.9.0`), `backend/README.md`.
- `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None changed. `interfaces/records.cddl` is read, by the drift test only.

## Acceptance criteria
- A batch of one to five records decodes to the same number of typed records, in the order sent.
- A faulted or unconfigured reading has `value` `None`. An out-of-range reading keeps the value as measured. Nothing is clamped or filled in.
- `t` is present exactly when `tk` is true, in scans and in both gap marks; otherwise the record is refused.
- Refused with `DecodeError`: not bytes, not CBOR, trailing bytes, not an array, 0 or more than 5 records, an unknown version, a record that is neither scan nor gap, a missing or unknown field, a wrong type or size, an unknown quality, a value on a fault or unconfigured reading or none on any other, `lost` below 1. The error names the record and the field.
- The whole message is checked before anything is returned.

## Test plan
pytest, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI. The fixture is five records from the simulator CLI (`--scans 5 --sntp-sync-after-ms 2500 --fault 2001:sensor_fault --fault 1001:out_of_range`), unframed, put in one CBOR array and checked against the schema by `tanksim.cddl` before it was saved. It is stored as hex in a `.txt` file because the root `.gitignore` ignores `*.hex` (firmware images). No bench test: nothing touches hardware.

## How records are checked against the schema
Three options were weighed:
1. **Field checks in the decoder now, plus a drift test on the schema file (taken).** No new dependency and no other component touched. The cost is that the rules exist twice. The drift test reads `records.cddl` and fails if the version, the batch size or the quality codes change there only. The `backend` CI job already runs on every `interfaces/` change.
2. **Depend on the simulator package.** That would tie the cloud runtime to a test tool, ship it in the backend image, and need `ci.yml` to run the backend job on simulator changes.
3. **Move `simulator/tanksim/cddl.py` to `shared/` so both use it.** This is the right long-term fix, but it changes the simulator and `ci.yml` and is its own story.

## Out of scope
A full CDDL check shared with the simulator (option 3). Storage, the database and Alembic, de-duplication by boot ID and sequence number, comparing `dev` with the topic's device ID, MQTT or IoT Core ingest, the managed queue, a dead-letter path for refused messages, any HTTP endpoint, level % and volume, Cognito, the Docker image, Terraform and the dashboard.

## Open questions [Confirm]
1. **A bare record is refused.** The schema's `start = batch / message` also allows a single record that is not wrapped in an array. The tech lead's brief for this story says to refuse anything that is not an array, because S-064 always publishes a batch on `tank/{device_id}/records` (taken).
2. **Stricter than the CDDL in three places:** `t` is required when `tk` is true; a good, stale or out-of-range reading must carry a value; `lost` must be at least 1. The schema states these in comments, not in rules, and both the firmware (`scan_builder.c`) and the simulator already follow them (recommended, taken).
3. **All or nothing:** one bad record refuses the whole message, so a batch is never half-stored. What happens to a refused message is for the ingest story (recommended, taken).

## PR checklist notes
Title `feat(dashboard): decode the CBOR batch message in the backend (S-067)`, branch `feature/S-067-backend-batch-decode`, `Closes #137`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
