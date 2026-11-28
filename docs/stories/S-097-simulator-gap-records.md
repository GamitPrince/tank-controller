# S-097: Simulator reports lost scans as a gap record

- Story ID: S-097 (issue #195).
- Epic: E3 (P1-02, P1-14). Points: 1. Priority: Should. Component: simulator. Review flag: one collaborator other than the author (S-010). Not a safety path.
- Part 3 of 3, stacked on S-096 (#194). The decisions and the `[Confirm]` items for all three parts are in [`S-095-simulator-batches.md`](S-095-simulator-batches.md).

## Goal

When the simulator's outage buffer is full, the scans it could not hold are not a silent hole: a gap record (S-040) reports them, in a batch, so a consumer such as the backend's gap table (S-069) can be tested from the simulator.

## Phase check

Phase 1, transmit only. The gap record is already in `interfaces/records.cddl` (S-040). Nothing new is read or written on a device.

## Decisions already made

- S-040: a gap record counts the lost scans and carries the boot id, seq, uptime and, when known, Unix time of the first and last of them. The cloud never interpolates across it.
- S-095: a gap record counts as one message in a batch and never cuts one.
- S-018: the simulator's buffer is append-only; when full, the new scan is lost and the history already held survives.

## Files to create or change

- New `simulator/tanksim/gap.py`: `gap_frame`, the framed gap record built from the first and last lost frames.
- `simulator/tanksim/link.py`: `BufferedLink` takes an optional gap builder and, after a backlog, delivers one gap record for the scans it lost. Without a builder it only counts them, as before.
- `simulator/tanksim/cli.py`: `--buffer-capacity N`, and the gap builder wired in.
- Tests: new `simulator/tests/test_gap.py`, additions to `test_batch.py` and `test_cli.py`.
- `simulator/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched

None.

## Acceptance criteria

1. With a full buffer, the lost scans arrive as one gap record after the buffered records and before the next live scan, with `lost` counting them and `first` and `last` carrying their time fields (`t` only when time was known).
2. One outage gives one gap record; an outage that loses nothing gives none.
3. Without a gap builder, `BufferedLink` behaves exactly as before.
4. In a batch, the gap record is one of the five messages and passes the `batch` rule.
5. Simulator CI is green with at least 80% line coverage.

## Test plan

Simulator pytest through `simulator/ci.sh` and the `simulator` CI job. Checked by hand: `decode_message` in the backend reads a batch holding the gap record (recorded in the S-095 PR).

## Out of scope

The FRDM's drop-oldest behaviour and its gap carry-forward (S-039, S-041); several gap records per outage.

## Open questions [Confirm]

1. **The gap record's frame sequence.** The framed `--output` stream gives the gap record the sequence number of the last lost scan, which was never sent, so the next live frame still follows it. Recommended, taken. Batches carry no frame sequence, so they are not affected.

## PR checklist notes

Title `feat(simulator): report lost scans as a gap record (S-097)`, branch `feature/S-097-simulator-gap-records`, `Closes #195`. Draft until S-096 merges; then merge `develop` in before review. No `safety` label. No interfaces change.
