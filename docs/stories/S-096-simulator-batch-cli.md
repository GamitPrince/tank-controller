# S-096: Simulator CLI writes batch messages

- Story ID: S-096 (issue #194).
- Epic: E3 (P1-02, P1-12). Points: 1. Priority: Should. Component: simulator. Review flag: one collaborator other than the author (S-010). Not a safety path.
- Part 2 of 3, stacked on S-095 (#193). The decisions for all three parts, all confirmed, are in [`S-095-simulator-batches.md`](S-095-simulator-batches.md).

## Goal

One command writes what a device would publish, so the backend decoder (S-067) can be fed from the simulator with no hardware, broker or cloud.

## Phase check

Phase 1, sense and transmit only. Output goes to a file; nothing is published to a network.

## Decisions already made

- S-095: `BatchSink`, five records to a batch, sooner on a prompt change (S-065), a shorter last batch at the end.
- S-064: the ESP32 publishes each batch unchanged as one MQTT message on `tank/{device_id}/records`.
- ADR-0004 decision 13 and ADR-0007: standalone simulator, no cloud account.

## Files to create or change

- `simulator/tanksim/cli.py`: `--batches PATH`, also accepted with `--replay`.
- `simulator/tests/test_cli.py`, `simulator/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched

None.

## Acceptance criteria

1. `--batches PATH` writes one batch per line, as lowercase hex of the CBOR array (the exact MQTT payload), with LF line ends, and the summary lists each batch and why it was cut.
2. Each line decodes and passes the `batch` rule; seven scans give batches of five and two, oldest first.
3. `--replay CAPTURE --batches PATH` regroups a framed capture into batches, records unchanged.
4. Without `--batches`, the command's output and `--output`'s framed stream are unchanged.
5. Simulator CI is green with at least 80% line coverage.

## Test plan

Simulator pytest through `simulator/ci.sh` and the `simulator` CI job. The backend cross-check is done by hand and recorded in the S-095 PR.

## Out of scope

Publishing to a broker or any network; batches as the default output (S-095 open question 1); gap records (S-097).

## Open questions (confirmed by the tech lead, 28 Nov 2026)

Both confirmed with S-095's items: 1 (an option, not the default) and 4 (hex lines).

## PR checklist notes

Title `feat(simulator): write batch messages from the simulator CLI (S-096)`, branch `feature/S-096-simulator-batch-cli`, `Closes #194`. Draft until S-095 merges; then merge `develop` in (no rebase, no force-push) before review. No `safety` label. No interfaces change.
