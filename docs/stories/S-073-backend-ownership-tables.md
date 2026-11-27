# S-073: Add the customer, plant, tank and device tables

- Story ID: S-073 (issue #149).
- Epic: E4 (groundwork for P1-20). Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path, and `.github/` is not touched.

## Goal
The backend database records who owns each device: customer > plant > tank > device, with each device's tank assignments kept as history. Once this lands, a read helper can say which tank, plant and customer a device is on, now or at a given time. The login story needs that answer before it can limit a request to one customer's data.

## Phase check
Phase 1, read-only for plant data. Five tables and one migration. There is no endpoint, no write API and no claim flow. Nothing is sent to a device. No cloud account and no AWS resource are used (ADR-0007's three gates still hold). Tests run on local SQLite files with made-up names.

## Decisions already made
- **ADR-0007 decision 2:** one shared multi-tenant cloud, modelled customer > plant > tank > device. Every user, query and device is held to its own customer. **Decision 5:** nothing is ever deleted.
- **ADR-0005 decision 2:** the QR code carries only the device ID. A device is unclaimed until an admin assigns it to a tank. Its data is held and not shown. Moving it to another tank needs an admin.
- **ADR-0008 decision 3:** a user belongs to one customer, optionally limited to plants or tanks. The backend checks this on every request.
- **S-068 to S-072:** the record tables are keyed by the records' `device-id` (`interfaces/records.cddl`, up to 64 bytes) and stay unchanged. The schema conventions also stand: named constraints, frozen-snapshot migrations, and DDL that works on both SQLite and Postgres.

## Files to create or change
- `backend/tankapi/db.py`: `CustomerRow`, `PlantRow`, `TankRow`, `DeviceRow`, `AssignmentRow`.
- `backend/migrations/versions/0003_ownership.py` (revises `0002`).
- `backend/tests/test_ownership.py`, `backend/tests/test_db_migrations.py`, `backend/tests/conftest.py` (the test engine switches on SQLite's foreign keys).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` is not changed. `devices.device_id` uses the same 64-byte limit as `device-id`.

## Acceptance criteria
- A plant belongs to one customer and a tank to one plant, through foreign keys. A name is unique within its parent, and customer names are unique.
- A device row is keyed by its device ID. `device_assignments` puts a device on a tank over `[valid_from_unix_s, valid_to_unix_s)` in Unix seconds UTC, the same time base as a scan's `t`. A row with no end is the current assignment. A partial unique index allows at most one open assignment per device.
- Check constraints: no name or device ID is empty, a start is never negative, and an end comes after its start. No foreign key cascades a delete, so a customer that still has plants cannot be deleted.
- A move closes the old assignment and opens the next, so both rows stay. A device taken off its tank keeps its closed row and has no open one.
- `scan_records`, `readings`, `gap_records`, `ingest_message` and the readings endpoint are unchanged.
- `alembic upgrade head` and `downgrade base` run cleanly with all three revisions. The models match the migrated schema, and the Postgres SQL renders offline.

## Test plan
pytest, run locally on Windows (Git Bash, `PYTHON=python bash scripts/ci/run-component.sh backend`) and in GitHub CI, on SQLite files that Alembic migrates. The tests cover:
- a made-up customer, plant, tank and device, with a second customer
- a device moved to another tank, keeping the old assignment
- a device taken off its tank
- every foreign-key, unique and check rule, and a refused delete
- upgrade and downgrade

No bench test is needed, because nothing touches hardware.

## Out of scope
**The read helper** that resolves a device ID to its tank, plant and customer, now or at a given time, or reports it unclaimed. It was written in this story and split out to the next story for PR size, with no migration needed. Also out of scope: users, roles and Cognito; per-customer filtering on the readings endpoint; the claim flow, QR codes and certificates; admin screens and any write endpoint; the audit trail; what happens to records from unclaimed devices; the TimescaleDB container, the queue consumer, the IoT Core rule, the Docker image, Terraform and the dashboard.

## Open questions [Confirm]
Questions 1, 5 and 7 concern this story and were confirmed by the tech lead on 27 Nov 2026. Questions 2, 3, 4 and 6 belong to later stories and stay open until those stories decide them.

1. **Assignments keep history** (confirmed 27 Nov 2026). The alternative was a `tank_id` column on the device row: simpler, but a move would re-file every old reading under the new tank, which could belong to another customer.
2. **Records from unclaimed devices** (for the login story). Ingest stores every record by device ID whatever its claim state, which is ADR-0005's "held". Recommended: show a reading only to the customer whose tank the device was on at the scan's `t`. Readings from before the claim (bench tests) or after a release then stay held and are shown to nobody. Still open: should a claim adopt earlier readings, and should records from a device missing from `devices` be refused or quarantined?
3. **Scans with no known time** (`tk` false) cannot be placed in an assignment. Recommended: no tank shows them until a later story decides, as S-072 does with `untimed`.
4. **Overlap among closed assignments** is not refused by the schema. Portable SQL cannot express it, and a Postgres exclusion constraint needs `btree_gist`. The claim and move story must close the old row and open the new one in one transaction. The read helper should raise if rows overlap anyway, rather than pick a customer.
5. **Integer IDs** for customers, plants and tanks (confirmed 27 Nov 2026). They are not secrets: isolation comes from the scope check on every request (P1-20, "including by guessing IDs").
6. **SQLite foreign keys** are enforced only when a connection asks for it. The test engine asks, and Postgres always enforces them. The app's own engine (`session.py`) is unchanged.
7. **Claim state is derived from assignments** (confirmed 27 Nov 2026), not stored as a flag, so the two cannot disagree. A device row holds only its ID. Provisioning details (certificate, label) belong to the provisioning story.

## PR checklist notes
Title `feat(dashboard): add the customer, plant, tank and device tables (S-073)`, branch `feature/S-073-backend-ownership-tables`, `Closes #149`. The `dashboard` scope follows S-066's [Confirm] 1. No `safety` label. `interfaces/` is not changed. About 370 changed lines, about half of them tests and docs; the read helper was split out to keep the PR near 300.
