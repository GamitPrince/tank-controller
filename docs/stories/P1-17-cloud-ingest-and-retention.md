# P1-17: Ingest and store telemetry in cloud time-series storage with a defined retention period

- Story ID: `[Confirm]` — not yet issued.
- Epic: E4 Cloud, alarms and access. Points: 5. Priority: Must. Component: dashboard (backend) per the card. Review flag: none.
- Status: **Gated. Cannot start until three gates pass.**

## Goal
Records arriving from devices are decoded, stored with their original timestamps, and queryable by signal and time range.

## Phase check
Phase 1. Receive and store only. The cloud **never** commands a device in Phase 1.

## THREE GATES before any cloud account is opened or paid for
ADR-0007 is explicit, and `AGENTS.md` section 11 forbids opening cloud accounts or adding paid services. All three must pass first:

1. The customers' answers (Siemens and Astec) on hosting, security and data residency.
2. An **early cloud test** — this comes before any account is opened.
3. A **Tiger Cloud quote** for 100 and 1,000 devices.

If a gate fails, the fallback in ADR-0007 decision 4 applies (Timestream for InfluxDB 3 plus managed PostgreSQL) or the decision is reopened. **Do not create AWS resources, sign up, or add a paid service under this story.** Local development against a container is fine.

## Decisions already made
- **ADR-0007:** managed AWS services; **IoT Core** as broker with our own CA; **one shared multi-tenant cloud** in our account, modelled customer > plant > tank > device; **Tiger Cloud** (managed TimescaleDB) on AWS **Mumbai** for readings and records; backend in **containers fed by a managed queue**, decoding CBOR; retention **raw archive forever, per-minute summaries forever, per-second 90 days**; the **calculation version is stored**; encryption in transit and at rest; a monthly cost budget and alert.
- **ADR-0004 decision 10:** volume and mass are computed **here**, in the cloud, not on the device. See the P1-04 conflict.
- **ADR-0008:** Python FastAPI backend, OpenAPI with generated TypeScript types, pytest, 80% coverage counting all code.
- **ADR-0009:** Terraform or OpenTofu blueprints, test and live copies, OIDC login, no permanent keys. **Third-party GitHub Actions are blocked**, which rules out the usual AWS and Terraform setup actions — use `run:` steps or ask.

## Acceptance criteria (from the story card)
- Telemetry is stored with original timestamps and can be queried by signal and time range.
- The retention period is configured. **Now specified by ADR-0007**, so the card's `[Confirm]` is answered: raw forever, per-minute forever, per-second 90 days.
- Buffered data forwarded after an outage creates **no duplicates** — pairs with P1-14 and the QoS 1 at-least-once delivery in ADR-0004.7, so de-duplication by sequence number and boot ID is required here.
- Plus: the calculation version is stored alongside computed values.

## Where does the backend live?
**Undecided** (`AGENTS.md` section 6; the card's question 2 assumed under `dashboard/`). Settle before starting, because it determines the `ci.sh` layout and the CODEOWNERS entry.

## Test plan
pytest against a local container stack: a managed-queue stand-in, Tiger Cloud or plain Postgres with Timescale locally, CBOR decode of simulator output, replay of a buffered outage batch to prove no duplicates, query by signal and range, retention policy applied. The early cloud test (gate 2) is a separate, deliberately small exercise.

## Dependency
P1-02, P1-03, P1-12, P1-14; the three gates; the backend location decision; the Terraform story that does not yet exist.

## Out of scope
Alarms (P1-18), stale flag (P1-19), login (P1-20), dashboard screens (E5). Opening any account.

## Open questions
- `[Confirm]` Where the backend lives in the repo.
- `[Confirm]` Who runs the early cloud test, and what counts as passing it.
- `[Confirm]` Does P1-17 own the volume and mass calculation moved here from P1-04, or does that need its own story? It is a geometry and density problem, not an ingest problem.
- `[Confirm]` Database migration tool — undecided.
