# S-059: Take a scan every second and log it

- Story ID: S-059 (issue #121).
- Epic: E3 (P1-12, P1-14). Points: 2. Priority: Must. Component: FRDM firmware. Review flag: one collaborator other than the author. Not a safety path.

## Goal
A thread builds one scan every second with the S-058 builder and appends it to the flash log. It runs whether or not a network is up. The uplink service (S-049) forwards the log on its own.

## Phase check
Phase 1, read-only. The inputs are read and never written; the only write is to the flash log.

## Decisions already made
- **Tech lead, 26 Nov 2026 (S-053 item 5):** one consolidated flash record per second. The FRDM acquires and logs from boot, independently of the network.
- **ADR-0004 decision 12, S-039:** always log first, forward from the log.
- **S-049:** the uplink service runs at `K_PRIO_PREEMPT(10)` with a module-owned stack and a semaphore for a prompt stop. This service follows the same pattern.

## Implementation
- `firmware/src/record/scan_service.h/.c`:
  - `tank_scan_service_start(svc, inputs, cfg)` starts one thread on a module-owned stack, at `K_PRIO_PREEMPT(5)`, above the uplink, so taking scans never waits for forwarding.
  - `tank_scan_service_stop(svc)` wakes and joins it.
  - `tank_scan_service_stats(svc)` gives the counters: scans, build errors, append errors, skipped grid points, last error.
- **Inputs:** the S-058 sources, the boot time and the flash log. An optional `k_mutex` is held while a scan is built; whoever updates the inputs or the boot time from another thread takes the same lock (S-060 wires it).
- **Grid:** the first scan is at once, then one every `period_ms` (1000 in Phase 1, passed in). Each wait runs to the next grid point, so the schedule does not drift with the scan's duration. `tank_scan_service_next_deadline()` is the pure policy: after an overrun it jumps to the first grid point still ahead and counts the ones missed, instead of catching up in a burst.
- **seq** starts at 1 each boot and advances for every scan built, so a scan the flash log failed to store shows as a gap in seq rather than disappearing.

## Interfaces touched
None.

## Acceptance criteria
- One scan per period, stored in seq order, with `up` on the period grid (no drift).
- A held input lock delays the scan; the grid points it missed are counted as skipped, and scanning resumes on the grid.
- Stop returns promptly while waiting; a second start returns `-EALREADY`; bad arguments return `-EINVAL`.
- A build error (no inputs) and an append error (unmounted log) are counted, and nothing invalid is logged.
- The existing suites pass, and 80% line coverage holds.

## Test plan
`native_sim` with the flash simulator, new suite `firmware/tests/record_scan_service`, using the real loop-level module as an input. No bench test.

## Out of scope
The application `main`, devicetree and real pin reads (S-060 and later). Health signals (a later story). A watchdog: it touches safe-state behaviour, so it needs its own story and the tech lead's go-ahead.

## Open questions [Confirm]
1. **Priority 5 for scans, 10 for the uplink** (recommended, taken): a slow link never delays a record.
2. **seq counts scans built, not scans stored** (recommended, taken): a flash failure becomes a visible seq gap.

## PR checklist notes
Title `feat(firmware): take a scan every second and log it (S-059)`, branch `feature/S-059-scan-service`, `Closes #121`. No `safety` label.
