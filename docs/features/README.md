# Feature Registry

Every finished feature, with the story that delivered it, where its code and tests live, and the pull request that merged it. It is the index P1-24 asks for. Repo chores, dependency bumps and documentation-only stories are left out; the status of every Phase 1 story is in [docs/stories/README.md](../stories/README.md).

Started 26 Nov 2026 (S-052) by back-filling the features merged so far. Each row points at the merged PR and spec instead of a separate Feature Completion Document; `completed/` is for those documents if the tech lead wants them from here on. Paths below are relative to the repository root. `firmware/src/` and `firmware/tests/` are shortened to `src/` and `tests/`.

## Interfaces and simulator

| Feature | Phase 1 story | Delivered by | Code | Tests |
| --- | --- | --- | --- | --- |
| Signal list v1 and CBOR record schema | P1-03 | S-017, PR #36 | `interfaces/signals-v1.yaml`, `interfaces/records.cddl` | checked by the simulator and firmware suites |
| Gap record for scans lost to a full buffer | P1-14 | S-040, PR #84 | `interfaces/records.cddl` | `tests/record_flash_log`, `tests/record_cbor` |
| Simulator: every signal, fault injection, outage replay | P1-02 | S-018, PR #38 | `simulator/tanksim/` | `simulator/tests/` |

## FRDM firmware: plant reads (all status-only, input-only)

| Feature | Phase 1 story | Delivered by | Code | Tests |
| --- | --- | --- | --- | --- |
| High-high and low-low level switches (DI 1-2, normally closed, 200 ms) | P1-05 | S-022, PR #46 | `src/safety/level_switch*` | `tests/safety` |
| Alarm and trip contacts (DI 10-15, normally closed, 200 ms) | P1-09 | S-031, PR #67 | `src/safety/alarm_input*` | `tests/safety_alarm` |
| Six PT100 product temperatures on the MAX31865 | P1-06 | S-032, PR #69 | `src/hardware/max31865*`, `src/measurement/pt100*`, `src/measurement/product_temperature*` | `tests/hardware_max31865`, `tests/measurement_pt100`, `tests/product_temperature` |
| Equipment status contacts (DI 3-9, normally open, 5 s) | P1-27 | S-033, PR #71 | `src/measurement/equipment_status*` | `tests/equipment_status` |
| Radar and pressure level 4-20 mA on the AD4111 | P1-04 (firmware half) | S-034, PR #73 | `src/hardware/ad4111*`, `src/measurement/loop_level*`, `src/measurement/scaling*` | `tests/hardware_ad4111`, `tests/measurement_loop_level`, `tests/measurement` |

## FRDM firmware: time, buffering and transmit

| Feature | Phase 1 story | Delivered by | Code | Tests |
| --- | --- | --- | --- | --- |
| SNTP plus boot-relative time, boot id, "time not yet known" | P1-15 | S-038, PR #80 | `src/communications/clock_sync*`, `src/communications/sntp_client*`, `src/record/boot_time*` | `tests/communications_clock_sync`, `tests/record_boot_time` |
| Delta-encoded append-only flash log, forwarded with original timestamps | P1-14 | S-039, PR #82 | `src/record/flash_log*`, `src/record/scan_codec*`, `src/communications/log_forwarder*` | `tests/record_flash_log`, `tests/record_scan_codec` |
| UART link framing (COBS, version, type, seq, CRC) | P1-12 | S-042, PR #88 | `shared/link-protocol/link_frame*` (moved from `src/communications/` in S-056) | `tests/communications_link_frame`, `esp32/tests/` |
| Delivery confirmation (stop-and-wait sender, duplicate-safe receiver) | P1-12 | S-043, PR #90 | `shared/link-protocol/link_sender*`, `shared/link-protocol/link_receiver*` (moved in S-056) | `tests/communications_link_delivery`, `esp32/tests/` |
| CBOR scan and gap records | P1-12 | S-044, PR #93 | `src/record/record_cbor*` | `tests/record_cbor` |
| Flash log forwarded over the link (partial acks) | P1-12 | S-045, PR #94 | `src/communications/uplink*` | `tests/communications_uplink`, `tests/record_flash_log` |
| Zephyr UART driver for the ESP32 link | P1-12 | S-048, PR #100 | `src/hardware/esp32_uart*` | `tests/hardware_esp32_uart` |
| Uplink service thread; flash log made thread-safe | P1-12 | S-049, PR #102 | `src/communications/uplink_service*`, `src/record/flash_log*` | `tests/communications_uplink_service` |
| One-second scan record built from the 23 inputs (scaled value, quality, age, boot-time header) | P1-12 | S-058, PR #120 | `src/record/scan_builder*` | `tests/record_scan_builder` |
| A scan every second, logged to flash on a drift-free grid | P1-12, P1-14 | S-059 | `src/record/scan_service*` | `tests/record_scan_service` |

## ESP32 firmware

| Feature | Phase 1 story | Delivered by | Code | Tests |
| --- | --- | --- | --- | --- |
| ESP32 end of the UART link | P1-12 | S-047, PR #98 | `esp32/components/link_endpoint/` | `esp32/tests/` |

## Not yet in the registry

Nothing reaches the cloud or a screen yet: P1-04's cloud half, P1-12's ESP32 network code and broker, P1-16 to P1-23, P1-25 and P1-26 are not built. See the status table.
