# S-071: Ingest one MQTT message in the backend

- Story ID: S-071 (issue #145).
- Epic: E4 (groundwork for P1-17). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend has one function that takes one MQTT message (its topic and payload) and either stores it or refuses it with a reason. A future queue consumer calls it once per message. A message from the wrong topic, or with records from another device, or that does not decode, is refused and writes nothing.

## Phase check
Phase 1, read-only. A function that writes to the backend's own database: no MQTT client, no broker, no queue, no endpoint, no cloud account and no AWS resource (ADR-0007's three gates still hold). The controller is send-only, so the ingest path publishes nothing and answers no device. Tests run on local SQLite files.

## Decisions already made
- **ADR-0004 decision 7 and amendment 4:** MQTT QoS 1 on `tank/{device_id}/records`, a batch of up to five one-second records per message.
- **ADR-0005 decision 6:** each device publishes only to its own topic. The broker policy enforces this later; the backend checks it too, so a record is never stored under a device it did not come from.
- **ADR-0007 / ADR-0008:** the backend decodes CBOR and stores the records; level %, volume and summaries are computed later, in the cloud.
- **S-067 / S-070:** `decode_message` returns typed records or raises `DecodeError`; `store_message` stores a message all or nothing and skips records already stored.
- **`interfaces/records.cddl`:** `device-id = tstr .size (1..64)`, counted in bytes.

## Files to create or change
- `backend/tankapi/ingest.py`: `ingest_message(session, topic, payload) -> Accepted | Refused`, and `device_from_topic(topic)`.
- `backend/tests/test_ingest.py`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

No migration and no new dependency.

## Interfaces touched
None changed. The topic shape and the `device-id` rule are read from ADR-0004 and the schema, not changed.

## Acceptance criteria
- A topic that is not exactly `tank/{device_id}/records`, with a device ID of 1 to 64 bytes, is refused. The reason quotes the topic, cut to 100 characters.
- A payload that does not decode is refused with the decoder's reason. Nothing is written.
- If any record's `dev` differs from the topic's device ID, the whole message is refused and the reason names the first such record. Nothing is written.
- A valid message is stored with `store_message`, and the result is `Accepted(stored, skipped)`. The same message delivered twice gives `Accepted(stored=0, skipped=5)` the second time.
- Every refusal is logged at WARNING with the standard `logging` module: device ID, reason and payload size, never the payload bytes. Nothing is printed.
- A database failure is raised, not turned into a refusal ([Confirm] 1).
- Nothing is published and no device is answered.

## Test plan
pytest, locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files migrated by Alembic:
- the simulator batch fixture accepted on `tank/SIM-0001/records`;
- the same message twice: everything skipped the second time;
- nine wrong topic shapes (missing or extra level, wrong prefix or suffix, wrong case, empty or 65-byte device ID, empty topic), and the 64-byte limit counted in bytes;
- a topic of another device, and a batch where only the last record is from another device;
- malformed payloads: not a batch, truncated CBOR, an empty batch, an empty `dev`;
- a refusal after a stored message leaves the database unchanged;
- a refusal logged at WARNING without the payload, with nothing printed; a valid message logs no refusal.

No bench test: nothing touches hardware.

## Out of scope
The IoT Core rule and broker policy; the managed queue and its consumer; any MQTT client or broker; a dead-letter store for refused messages (a later story: refusals are only logged today); metrics and alarms on refusals; the customer > plant > tank > device tables and the claim flow (an unknown or unclaimed device is not checked yet); the TimescaleDB container and retention; HTTP endpoints; level % and volume; Cognito; the Docker image; Terraform; the dashboard.

## Open questions [Confirm]
1. **Refusals are results, failures are exceptions** (recommended, taken). A refused message would be refused again however often it is delivered, so the consumer should drop it (or, later, dead-letter it) and acknowledge it. A database error may pass on a retry, so it is raised and the consumer leaves the message for redelivery; `store_message` has already rolled it back.
2. **The topic is checked by the backend as well as the broker** (recommended, taken). The IoT Core policy will limit each certificate to its own topic (ADR-0005), but a misconfigured rule or a test client must still not get a record stored under the wrong device.
3. **Refusals are logged at WARNING, with no rate limit.** A device stuck sending bad messages would log one line per message (one every 5 s). Metrics and alarms are a later story.

## PR checklist notes
Title `feat(dashboard): ingest one MQTT message in the backend (S-071)`, branch `feature/S-071-backend-ingest-handler`, `Closes #145`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed.
