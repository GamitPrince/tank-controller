# S-095: Simulator sends batch messages

- Story ID: S-095 (issue #193).
- Epic: E3 (P1-02, P1-12). Points: 1. Priority: Should. Component: simulator. Review flag: one collaborator other than the author (S-010). Not a safety path.
- **Split (about 680 changed lines in one piece, AGENTS.md section 0 item 4):** S-095 is the batch sink, S-096 (#194) the CLI option that writes batches, S-097 (#195) gap records from the outage buffer. They are stacked in that order, and the decisions for all three are here.

## Goal

The simulator can group its records the way a device does before publishing: batch messages of one to five complete records, oldest first, each the payload of one MQTT message on `tank/{device_id}/records`. Its output can then be fed to the backend decoder (S-067), so the chain from simulator to backend runs locally with no hardware, broker or cloud.

## Phase check

Phase 1, sense and transmit only. It changes how simulated records are grouped, not what they hold. No new signal, field or inbound message; the simulated device stays send-only and nothing is published to a network.

## Decisions already made

- **S-062:** `batch = [1*5 message]`, `message = record / gap-record`, complete records, oldest first. A single message stays valid on its own.
- **S-063:** five records per frame; a backlog after an outage drains five at a time.
- **S-064:** the ESP32 publishes each batch unchanged as one MQTT message on `tank/{device_id}/records`.
- **S-065:** a batch is sent at once when, against the scan before it, any reading's quality or value presence changes, any contact's value changes, or the scans do not line up. Analogue values do not count. The contacts are the digital inputs.
- **S-040:** when the outage buffer drops scans, a gap record says so; the cloud never interpolates across it.
- **ADR-0004 decision 13:** standalone simulator, same schema, fault injection, outage replay with original timestamps.
- **ADR-0007:** no cloud account; output goes to files or stdout only.

## Files to create or change

- New `simulator/tanksim/batch.py`: `BatchSink`, a link sink that groups delivered records into batches, and `is_prompt_change`, S-065's rule.
- `simulator/tanksim/link.py`: `FanOutSink`, so one link can feed the framed stream and the batch sink together (used by S-096).
- Tests: new `simulator/tests/test_batch.py`, one test in `test_link.py`.
- `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched

None. `interfaces/records.cddl` already has the batch (S-062). Every batch is checked against its `batch` rule before it leaves the sink.

## Acceptance criteria

1. Steady scans go five to a batch; closing the sink at the end of a run sends a shorter last batch.
2. A live scan that is a prompt change (S-065) ends its batch at once, after that scan. Analogue noise does not; a contact change, a quality change, a value appearing or disappearing, and scans that do not line up do. Health flags are not contacts.
3. After an outage the backlog goes out oldest first, five to a batch, each record keeping its original `up`, `tk` and `t`. Replayed records do not cut a batch on a change.
4. A gap record counts as one message and never cuts a batch by itself.
5. No batch holds more than five messages; a batch limit outside 1 to 5 is refused.
6. Every batch passes the simulator's own CDDL check of the `batch` rule.
7. The framed single-record stream and every existing test are unchanged. Simulator CI is green with at least 80% line coverage.

## Test plan

Simulator pytest through `simulator/ci.sh` (in Git Bash: `PYTHON=python bash scripts/ci/run-component.sh simulator`) and the `simulator` CI job. No bench test: nothing touches hardware.

**Cross-check with the backend.** A test that feeds a simulator batch to `backend/tankapi/records.py` would make one component import the other, so there is none. Done by hand instead and recorded in the PR: the batch from `--scans 5 --sntp-sync-after-ms 2500 --fault 2001:sensor_fault --fault 1001:out_of_range --batches` (S-096) equals `backend/tests/fixtures/simulator-batch-cbor-hex.txt` (S-067) apart from the random boot id, so the fixture is not refreshed, and `decode_message` reads every batch, gap records included.

## Out of scope

- Publishing to an MQTT broker, or any network.
- The CLI option (S-096) and gap records from the outage buffer (S-097).
- Making the framed `--output` stream carry batches, as the S-063 link does.
- A rate limit on prompt changes (S-065 leaves it out too).
- The FRDM dropping the oldest records when its flash log is full (S-041); the simulator's append-only buffer keeps dropping the newest, as before.

## Open questions [Confirm]

1. **Default or option.** Recommended, taken in S-096: batches are an option, `--batches PATH`, and the framed single-record `--output` stays as it is. `--replay` reads that stream, and a single message is still valid (S-062). Making batches the default, and the framed stream carry batches, can follow once a consumer needs it.
2. **How a batch is cut.** Recommended, taken: after five messages; after a live scan that is a prompt change (S-065's rule, the first scan counting as no change); and at the end of a run. A gap record counts as one message and never cuts a batch by itself.
3. **Outage replay and faults.** Recommended, taken: the backlog drains five to a batch, as S-063's poll does when it finds a full batch; a change inside the backlog does not cut it. In S-097 a gap record follows the buffered records it was dropped after. Fault injection works unchanged: a fault that starts or ends changes a quality, so it cuts a batch.
4. **Output format.** Recommended, taken in S-096: one batch per line, lowercase hex, LF. It can be diffed and pasted, and matches the backend fixture's hex form (`.gitignore` ignores `*.hex`, so a saved fixture keeps the `.txt` name).

## PR checklist notes

Title `feat(simulator): send batch messages from the simulator (S-095)`, branch `feature/S-095-simulator-batches`, `Closes #193`. No `safety` label. No interfaces change.
