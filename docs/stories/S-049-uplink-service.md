# S-049: Run the forwarder in its own thread (P1-12, seventh slice)

- Story ID: S-049 (issue #101).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
The FRDM's send path (flash log, `log_forwarder`, uplink, UART driver) runs by itself: an uplink service thread polls the forwarder, drains a backlog as fast as the link allows, waits a short time when caught up, and backs off when the link is down. The flash log becomes safe to use from two threads at once, so a scan thread can append while the service forwards.

## Phase check
Phase 1, transmit only. The service only forwards what is already in the flash log; it receives nothing but S-043's DELIVERED confirmations and never acts on anything received. Nothing here touches the safety chain or `firmware/src/safety/`.

## Decisions already made
- **ADR-0004 decisions 3, 6 and 12:** the FRDM keeps the data and the buffer, always logs first and forwards from the log; records are batched when catching up.
- **ADR-0003:** Zephyr 4.5.0, C11; ztest and Twister on `native_sim`; 80% line coverage.
- **S-039, S-045:** `tank_log_forwarder_poll()` returns the number delivered, 0 when caught up, or a negative error when the link acknowledged none. A send can block for up to the link's ack timeout times its attempts for each record in the batch.

## Why a lock is needed
`struct tank_flash_log` has one shared frame buffer and read, write and ack positions, and no lock. Today only tests call it, from one thread. Once a scan thread appends while the service reads and acks, two calls can interleave and corrupt an entry or a position.

## Implementation
1. **Flash log lock** (`firmware/src/record/flash_log.h/.c`): a `struct k_mutex` inside `struct tank_flash_log`, initialised by `tank_flash_log_mount()`. `append`, `read_next`, `ack` and `rewind` each take it for the length of the call. `lost_scans` reads one 32-bit counter and stays lock-free. The forwarder never holds the lock across a send: it reads its batch, releases, sends, then acks, so appends are never blocked by a slow link.
2. **Uplink service** (`firmware/src/communications/uplink_service.h/.c`):
   - `struct tank_uplink_service_config { idle_ms, retry_ms }`.
   - `tank_uplink_service_next_delay(result, cfg)`: the pure policy. A result above 0 → 0 ms (poll again at once, the log may hold more); 0 → `idle_ms`; below 0 → `retry_ms`.
   - `tank_uplink_service_start(svc, fw, cfg)`: starts one thread, on a stack the module owns, that loops: poll, count the result, sleep the next delay. Returns 0, `-EINVAL` or `-EALREADY`.
   - `tank_uplink_service_stop(svc)`: asks the thread to finish after its current poll, wakes it and joins it. Used by tests and by a future orderly shutdown.
   - Counters: polls, items delivered, errors (polls that delivered nothing because of an error), last error code.
3. Default timing: **`idle_ms` = 1000, `retry_ms` = 5000**, passed in by the caller (no hardcoded values in the module). Thread priority and stack size are module constants.

## Interfaces touched
None in `interfaces/`. No change to the frame format, the record schema or the forwarder's API.

## Acceptance criteria
- With a backlog bigger than one batch, the service drains it batch after batch without waiting `idle_ms` between batches.
- Caught up, it polls about every `idle_ms`. After an error it waits `retry_ms` before polling again, and recovers once the link returns. Both are measured on the kernel clock.
- Stop returns promptly while the thread is sleeping, and a second start before stop returns `-EALREADY`.
- **Concurrency:** a test thread appends scans while the service forwards them; at the end every scan was delivered exactly once and in order, and the log reports no lost scans.
- The existing flash log, forwarder and end-to-end suites still pass unchanged.
- 80% line coverage on the new code.

## Test plan
`native_sim`, new suite `firmware/tests/communications_uplink_service`, using the flash simulator and a scripted `send_fn` (records what it was given, can fail N times). The concurrency test runs the real flash log with an appender thread. No bench test.

## Dependency
S-039, S-045, S-048 (merged).

## Out of scope
The firmware application itself (`main.c`, board config) and the scan thread that builds scans from the readings: there is no app yet, so wiring at boot is a later story. Choosing the path (Ethernet or the ESP32, ADR-0004 decision 8). The FRDM board overlay. Anything on the ESP32.

## Open questions [Confirm]
1. Put the lock **inside the flash log** (recommended: no caller can forget it), rather than an optional mutex that the forwarder and the scan thread share.
2. A **dedicated thread** (recommended: a send can block for seconds, which must not stall the system work queue), rather than a delayable work item.
3. Default **idle 1000 ms, retry 5000 ms** (recommended: well inside ADR-0004 decision 8's roughly 10 s failover window).
4. Name and place: `communications/uplink_service`.

## Decisions (tech lead, 26 Nov 2026)
All four recommendations were accepted: the lock lives inside the flash log; a dedicated thread; idle 1000 ms and retry 5000 ms by default; `communications/uplink_service`.

## Known limitation
A batch the forwarder has read but not yet acked can be dropped by an append that fills the ring (catching up after an outage longer than the log holds). Those scans are then both delivered and counted in the gap, so the gap can overstate the loss but never hide it. Recorded in `flash_log.h`.

## PR checklist notes
Title `feat(firmware): run the log forwarder in its own thread (S-049)`, branch `feature/S-049-uplink-service`, `Closes #101`. No `safety` label. CHANGELOG entry under Unreleased.
