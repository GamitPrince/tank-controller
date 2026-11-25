# S-048: Drive the FRDM-to-ESP32 UART from Zephyr (P1-12, sixth slice)

- Story ID: S-048 (issue #99).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
The uplink (S-045) gets real `read_fn`, `write_fn` and `now_fn` backed by a Zephyr UART, so the FRDM's whole send path runs on a real driver: flash log, forwarder, uplink, UART. Bytes received from the ESP32 are buffered by an interrupt handler and decoded into frames; frames to the ESP32 are written out byte by byte.

## Phase check
Phase 1, transmit only. The FRDM writes RECORD frames and reads back only DELIVERED (S-043). **Nothing received is acted on as a command**; frames other than DELIVERED are ignored by the sender. Nothing here touches the safety chain or `firmware/src/safety/`.

## Decisions already made
- **ADR-0004 decision 4:** the FRDM-ESP32 link is a UART.
- **ADR-0003:** Zephyr 4.5.0, C11; ztest and Twister on `native_sim`; the hardware layer is covered by the 80% gate.
- **S-045:** `tank_uplink_read_fn` waits up to `timeout_ms` for one decoded frame and returns 0, `-EAGAIN` on timeout, or an error; `tank_link_write_fn` writes a whole frame; `now_fn` is milliseconds.

## Implementation
`firmware/src/hardware/esp32_uart.h/.c`. Hardware layer, next to the AD4111 and MAX31865 drivers.

- `struct tank_esp32_uart` holds the UART device, a receive ring buffer, a semaphore the interrupt handler gives, an S-042 frame decoder and counters.
- `tank_esp32_uart_init(u, dev)`: checks the device is ready, installs the interrupt callback and enables receive interrupts. Returns 0, `-EINVAL` or `-ENODEV`.
- **Receive:** the interrupt handler moves bytes from the UART FIFO into the ring buffer and gives the semaphore. If the ring is full the extra bytes are dropped and counted; the decoder then rejects the damaged frame, resynchronises at the next delimiter, and S-043's resend recovers.
- `tank_esp32_uart_read(ctx, msg, timeout_ms)` (a `tank_uplink_read_fn`): feeds buffered bytes to the decoder until a frame is complete; otherwise waits on the semaphore for the time remaining. Returns 0, `-EAGAIN` once `timeout_ms` has passed, or `-EINVAL`.
- `tank_esp32_uart_write(ctx, bytes, len)` (a `tank_link_write_fn`): `uart_poll_out()` for each byte. Polled transmit: a worst-case record frame is about 1 KB, roughly 90 ms at 115200 baud, once per scan and only from the forwarder's thread; interrupt or async transmit can come later if profiling asks for it.
- `tank_esp32_uart_now(ctx)` (a `tank_uplink_now_fn`): `k_uptime_get_32()`.
- Counters: bytes received, bytes dropped on a full ring, frames decoded, frames rejected.
- The UART is found through a devicetree chosen node, `tank,esp32-uart`. The board's UART instance, pins and baud rate belong in the FRDM board overlay, which waits on the EE's pin mapping (ADR-0002); the spec assumes 115200 baud, 8N1 until then. The test overlay points the chosen node at Zephyr's UART emulator.

## Interfaces touched
None in `interfaces/`. No change to the frame format or to the uplink's function types.

## Acceptance criteria
- A frame that arrives in several chunks, with gaps, is returned by one read call once it is complete.
- A read with nothing arriving returns `-EAGAIN` after its timeout and not before, measured on the kernel clock.
- Garbage and a corrupted frame before a good one are counted and skipped; the good frame is returned.
- Bytes beyond the ring's capacity are dropped and counted, and the next whole frame is still received.
- A frame written is exactly the bytes the emulator sees on its transmit side.
- End to end on `native_sim`: a real flash log, `log_forwarder`, `uplink` and this driver, with an emulated ESP32 built from S-043's `link_receiver` answering DELIVERED over the emulated UART. A batch of scans is confirmed and acked; with the first DELIVERED lost, S-043's resend recovers and the record is confirmed once.
- 80% line coverage on the new code.

## Test plan
`native_sim`, new suite `firmware/tests/hardware_esp32_uart`, using Zephyr's `zephyr,uart-emul` driver (interrupt-driven receive, `uart_emul_put_rx_data()` to inject bytes, `uart_emul_get_tx_data()` and the transmit-ready callback to see what was written). No bench test: the board overlay is not part of this story.

## Dependency
S-042, S-043, S-045 (merged). The ESP32 side (S-047) is not needed: the test's emulated ESP32 uses `link_receiver` directly.

## Out of scope
The FRDM board overlay (UART instance, pins, baud), which waits on the EE. The thread or work item that runs `log_forwarder` periodically and wires everything together at boot. Interrupt or async transmit. Hardware flow control. Anything on the ESP32.

## Decisions (tech lead, 25 Nov 2026)
All four recommendations were accepted:
- The module lives in `firmware/src/hardware/`.
- Polled transmit for Phase 1.
- 115200 baud, 8N1, until the EE fixes the board overlay.
- The chosen node is named `tank,esp32-uart`.

## PR checklist notes
Title `feat(firmware): drive the FRDM-to-ESP32 UART from Zephyr (S-048)`, branch `feature/S-048-frdm-uart-driver-glue`, `Closes #99`. No `safety` label. CHANGELOG entry under Unreleased.
