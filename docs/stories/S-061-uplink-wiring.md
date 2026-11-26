# S-061: Wire the uplink into the application, with the factory device ID

- Story ID: S-061 (issue #125).
- Epic: E3 (P1-12). Points: 2. Priority: Must. Component: FRDM firmware. Review flag: one collaborator other than the author. Not a safety path.

## Goal
The firmware application forwards its flash log to the ESP32. Scanning starts first and never waits for the link. Each record is sent with the device's factory ID.

## Phase check
Phase 1, transmit only. The uplink forwards what the flash log holds and acts on nothing it receives except DELIVERED confirmations (S-043).

## Decisions already made
- **Tech lead, 26 Nov 2026 (this story):** the device ID is the MCU's factory unique ID, read with Zephyr's hwinfo API.
- **ADR-0005 decision 2:** the QR code carries only the device ID. The provisioning bench step records it and prints the label.
- **Tech lead, 26 Nov 2026 (S-053 item 5):** the FRDM logs from boot independently of the network, and buffered records go out when connectivity is there.
- **S-039:** forwarder batch 16 to 32. **S-049:** uplink idle 1000 ms, retry 5000 ms, passed in by the caller.
- **S-043, S-045:** the link sender's default timing; one record per frame, stop-and-wait.

## Implementation
- **`firmware/src/app/device_id.h/.c`.**
  - `tank_device_id_format()` writes a factory ID as lowercase hex.
  - `tank_device_id_read()` reads the ID with `hwinfo_get_device_id()` and formats it. An ID longer than 16 bytes is refused rather than cut short.
  - The MCX N's 16-byte ID gives 32 characters. That is the record encoder's limit (`TANK_RECORD_DEV_ID_MAX`), so the ID carries no prefix.
- **`tank_app` additions.**
  - Two new configuration fields: `esp32_uart` (`NULL` means log without forwarding) and `device_id` (required with a UART).
  - Once scanning runs, `tank_app_start()` starts the uplink: the ESP32 UART driver (S-048), the uplink (S-045) with the link sender's default timing, the log forwarder with a batch of 16, and the uplink service (S-049).
  - If only the uplink fails, scanning keeps running.
  - `tank_app_stop()` stops the uplink first, then scanning.
- **`firmware/app/`.**
  - `main.c` reads the device ID, takes the ESP32 UART from the devicetree's chosen `tank,esp32-uart` and passes idle 1000 ms and retry 5000 ms. With no device ID it still logs, just without forwarding.
  - The native_sim overlay adds an emulated UART for the link; `boards/native_sim*.conf` turn on the emulator subsystem.
  - The FRDM overlay will name the real UART (the EE's pin mapping).
- **`firmware/cmake/tank_app_sources.cmake`:** adds the uplink path, the CBOR encoder, the link library and the device ID.

## Interfaces touched
None.

## Acceptance criteria
- **No answer from the ESP32:** with nothing answering on the UART, scanning goes on at its own rate. The uplink tries, and nothing is confirmed.
- **ESP32 confirms:** with an emulated ESP32 that confirms each record, the records reach it, every one is confirmed, and the flash log is drained apart from at most the last in-flight record or two.
- **Device ID required:** a UART without a device ID is refused.
- **Device ID format:** the ID is the factory ID in lowercase hex. A buffer too small for it, an ID too long, NULL arguments and an empty ID are each refused.
- **Builds and tests:** the application builds for native_sim. Existing suites pass, and 80% line coverage holds.

## Test plan
`native_sim`. The `firmware/tests/app_tank_app` suite gains `src/uplink.c`, which uses the UART driver tests' emulated UART with an emulated ESP32 built from the S-043 receiver. No bench test yet: the real FRDM-to-ESP32 run is the end-to-end integration test the tech lead listed as outstanding.

## Out of scope
- **ESP32 side:** its Wi-Fi, TLS, MQTT and 4G code.
- **Real board files:** the FRDM board overlay and its UART pins.
- **Other application work:** clock-sync wiring, health signals, and the `health_cloud_link_up` signal.
- **A watchdog.**

## Open questions [Confirm]
1. **Forwarder batch of 16** (recommended, taken): the low end of S-039's range, which keeps RAM at about 10 KB.
2. **The MCXN947's hwinfo driver** is not yet proven on the board. If it reports no unique ID (`-ENOSYS`), the device logs but does not forward until that is fixed. The FRDM bring-up story checks this.

## PR checklist notes
Title `feat(firmware): wire the uplink into the application with the factory device ID (S-061)`, branch `feature/S-061-uplink-wiring`, `Closes #125`. No `safety` label.
