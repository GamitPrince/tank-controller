# S-062: Add the batch message to the record schema

- Story ID: S-062 (issue #127).
- Epic: E3 (P1-12). Points: 1. Priority: Must. Component: interfaces, simulator tests. **Review flag: `interfaces/` changes, so one approval from a collaborator other than the author** (S-010).

## Goal
The record schema says what a device actually sends: a batch of one to five records, packed into one FRDM-to-ESP32 link frame and published as one MQTT message.

## Phase check
Phase 1, transmit only. No new signal, field or inbound message. The device stays send-only.

## Why
- **The conflict:** the 26 Nov 2026 decision sends five one-second records in one MQTT message every 5 s on `tank/{device_id}/records`. The UART link is stop-and-wait (S-043), and the ESP32 confirms a record only after the cloud acknowledges it (S-047). So the ESP32 cannot gather five separate records: the FRDM waits on the first.
- **The fix (tech lead, 26 Nov 2026, this session):** the FRDM packs up to five records into one frame (S-063). The ESP32 publishes that frame unchanged as one message and confirms it once the cloud acknowledges it (S-064).

## Decisions already made
- **ADR-0004 decisions 6 and 12, amendment 4:** CBOR records with a CDDL schema; MQTT topic `tank/{device_id}/records`, five one-second records every 5 s, backlog oldest first.
- **ADR-0004 decision 3:** the FRDM keeps the buffer; the ESP32 holds nothing it has not had confirmed.

## Implementation
`interfaces/records.cddl`:

```
start = batch / message
batch = [1*5 message]
message = record / gap-record
```

- Records keep their order, oldest first.
- Each record stays complete with `v` and `dev`, so a consumer can split a batch and handle one record at a time.
- A single message is still valid on its own, which keeps the simulator and any per-record consumer working.
- `v` stays 1: no device or cloud consumes the schema yet, as when S-040 added the gap record.

`interfaces/README.md` mentions the batch. Its out-of-date note that the MQTT topic is undecided is fixed: the topic is not part of a record and is set by the ESP32 and the broker policy.

## Interfaces touched
`interfaces/records.cddl` (a new top-level rule; existing rules unchanged) and `interfaces/README.md`.

## Acceptance criteria
- Batches of one to five messages, scan and gap records mixed, pass the schema.
- An empty batch, a batch of six, and a batch holding a bad record are rejected.
- Every existing record and gap-record test still passes, using the default `start` rule.

## Test plan
Simulator pytest (`simulator/tests/test_cddl.py`), the schema-driven validator in the `simulator` CI job.

## Out of scope
- **FRDM packing:** packing up to five records per frame, and raising the link's 1,024-byte payload limit to fit five records of up to about 1,004 bytes each (S-063).
- **ESP32 publisher:** S-064.
- **Simulator output:** the simulator emitting batches (it still emits single records, which stay valid).

## Open questions [Confirm]
1. **NFR-01 and the 5 s batch.** Batching adds up to about 5 s to the oldest record in a batch, which strains NFR-01's 5 s end-to-end target for an alarm change. S-063 will propose sending at once when a contact or a quality changes.

## PR checklist notes
Title `feat(interfaces): add the batch message to the record schema (S-062)`, branch `feature/S-062-batch-message`, `Closes #127`. No `safety` label. Interfaces checklist item: another collaborator asked to review.
