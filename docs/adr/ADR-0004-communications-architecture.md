# ADR-0004: Communications architecture, data format and simulator

- Status: **Accepted.** Confirmed by the tech lead on 17 Nov 2026; approved by prinz-assists, a collaborator other than the author, and merged on 20 Nov 2026 in PR #12.
- Date: 2 Nov 2026
- Story: P1-00 (issue S-002); shapes P1-02, P1-03, P1-04, P1-11 to P1-17
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0002 (hardware), ADR-0003 (firmware)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

RSD FR-COM-01, 03, 04, 05 and NFR-01, 04, 05 require data to reach the cloud within 5 s, buffered through outages with original timestamps, clocks that agree, no open inbound ports, and stale or failed data shown as such. The first story-card plan assumed a separate gateway that polls the controller over Modbus. The project has instead chosen: the FRDM-MCXN947 collects the data and communicates itself, with Ethernet or Wi-Fi as the primary path (the client decides) and 4G as backup. Wi-Fi and 4G come from an ESP32-S3 + A7672S board (K-tron listing, specifications not yet verified) mounted in the same panel.

## Decisions

1. **Structure:** there is no separate gateway. The FRDM board collects the data and communicates to the cloud. The Modbus polling design of the first story-card plan is dropped for Phase 1.
2. **Uplink paths:** primary is Ethernet (on the FRDM board) or Wi-Fi (on the ESP32 board), whichever the client has. If the primary fails, 4G (on the ESP32 board) is used.
3. **ESP32 role:** a communications helper. The FRDM keeps the data and the buffer, hands records to the ESP32, and the ESP32 sends them over Wi-Fi or 4G and reports delivery. With Ethernet, the FRDM sends directly. There are two sending paths but one record format and one buffer.
4. **FRDM-to-ESP32 link:** a UART serial cable (same panel). RS-485 is not needed for this link. SPI was not chosen.
5. **Link protocol:** a small protocol of our own: framed messages (a standard framing method such as COBS), sequence numbers, CRC and delivery confirmation, with message types for "send this record", "delivered", "link status" (Wi-Fi and 4G state, signal strength) and "time". One small C library is shared by both boards and tested on a laptop. AT commands and Modbus were not chosen.
6. **Data format:** CBOR records with a written schema (CDDL) kept in `interfaces/`; code is generated from it for the firmware, the backend and the simulator. Records are batched when catching up. JSON and Protobuf were not chosen (size on the buffer and the metered 4G plan).
7. **Transport:** MQTT over TLS with acknowledged delivery (QoS 1) and per-device certificates, outbound connections only. If the client firewall blocks the standard MQTT secure port, MQTT over WebSocket on port 443 is used (decided when the pilot network is known). HTTPS POST was not chosen.
8. **Failover:** two tiers. The ESP32 switches between Wi-Fi and 4G on its own and reports its state. The FRDM chooses between Ethernet and the ESP32. A path counts as failed when the cloud has not acknowledged for about 10 s [Confirm; configurable, tuned in testing]; this keeps failover inside the 30 s stale-data limit of P1-19. A path counts as recovered after it has worked steadily for a few minutes [Confirm]. The ESP32 may keep the 4G module registered on the network while idle to speed up a switch.
9. **Signal list (replaces the register map of P1-03):** one versioned YAML file in `interfaces/` defining every Phase 1 signal with a numeric ID, name, unit, scale, update rate and a read-only flag. Records identify signals by ID and carry one timestamp per scan. All three developers review changes to it.
10. **Volume and mass:** calculated in the cloud backend from the tank geometry table and a temperature-corrected density for the selected product, not in the firmware. The firmware sends level and temperatures with quality flags. The controller is therefore send-only in Phase 1: it accepts no configuration from the cloud (firmware update and time are covered in the security ADR).
11. **Timestamps:** the FRDM syncs time over SNTP on whichever path works (the ESP32 passes it on its path). Every record also carries time since boot and a boot ID. Records made before the real time is known are marked "time not yet known", and a later message ties the boot ID to real time so the cloud can correct them. Cloud arrival time is never used as the measurement time.
12. **Buffer:** a compact lossless append-only log in the FRDM's external flash, each record with a checksum so a power cut cannot corrupt it. It uses delta encoding with regular full snapshots, is sized to hold 24 h in the flash left after the firmware-update slots, and when full drops the oldest data and records a gap event. Size estimate: about 10 MB per day if every value is stored each second, against about 8 MB of flash shared with the firmware slots. The expected saving from delta encoding (about 1 to 3 MB per day) is an estimate and must be verified on real data. An SD card is the fallback if it does not fit.
13. **Simulator (P1-02):** a standalone Python simulator that publishes records with the same schema and signal list over MQTT, runs on Windows without WSL2, and starts from one command. Faults (sensor fault, out-of-range value, link drop) are injected through a local control, never by sending commands to a device. It can replay an outage and send the backlog later with the original timestamps, to test the no-duplicates rule of P1-17. Running the real firmware on `native_sim` as a simulator is not part of Phase 1 and may be added later as a firmware integration test.

## Consequences

- **Story cards need updating** (the approved backlog of 26 Oct assumed a gateway): P1-11 (polling Modbus) is mostly obsolete; P1-12 (MQTT) and P1-14 (buffer) move into firmware; P1-15 (clock sync) becomes SNTP on the FRDM; P1-03 becomes the signal list; P1-04 no longer computes volume and mass (the backend does); P1-13 (OPC UA) and P1-16 (VPN-only access) are unresolved (see below). A new story is needed for the ESP32 firmware and for the cloud-side volume and mass calculation. Estimates need review. [Confirm]
- **RSD:** NFR-09 ("one gateway handles several tanks") no longer holds; each tank has its own controller. FR-COM-01 mentions Modbus RTU/TCP and OPC UA; with no gateway these need rewording or moving. FR-COM-05 requires VPN-only remote access, which a microcontroller cannot easily run; the security ADR decides whether outbound-only TLS with device certificates satisfies it and whether the RSD is amended. [Confirm]
- **Firmware effort rises:** the FRDM now carries MQTT over TLS, the flash log, failover and time sync, on top of the sensor work and the effort from ADR-0003 decision 10. A second firmware (ESP32) must be built and maintained, with its own framework, language and test tooling (not decided here).
- The no-inbound-ports rule holds by design: the FRDM and the ESP32 only make outbound connections. With no gateway, the FRDM and the ESP32 sit directly on the client's network, so the security design matters more.
- The controller has no inbound command channel in Phase 1, which keeps the read-only proof (P1-10) simple.

## To verify (early, in P1-01 and P1-04 and a communications spike)

- MQTT over TLS runs on the FRDM within its memory (the Zephyr board page lists 320 KiB RAM for the default configuration) alongside the sensor tasks and the flash log.
- The CBOR library with schema-based code generation (zcbor) works in Zephyr 4.5.
- The real size of the log with delta encoding, and the flash left after the firmware slots.
- The ESP32 board's exact specifications: Wi-Fi, A7672S bands for India, UART pins, power input, antenna connectors, temperature rating against about 50 C ambient.
- The ESP32 can do Wi-Fi to 4G failover reliably, and TLS and MQTT on both.
- The client network allows the chosen MQTT port, or WebSocket on 443.
- Time to fail over and reconnect stays under 30 s in practice.

## Not decided here

- Security design: device certificate handling, firmware-update and signing keys, the VPN question, ESP32 as a network path (security ADR).
- ESP32 firmware framework, language and tests (needs its own ADR).
- Cloud: MQTT broker, topic structure, ingestion, database and retention (cloud ADR).
- OPC UA in Phase 1 (RSD FR-COM-01, P1-13): unchecked on a microcontroller; may be served from the cloud side.
- Whether a local read-out (for a client PLC or a maintenance laptop) is wanted. Not provided in Phase 1.
- Whether to send less data on 4G to save the SIM plan.
- The channel allocation of the signal list, which depends on the EE's answers.

## References

- RSD v0.2: FR-COM-01, 03, 04, 05; FR-SAF-04; NFR-01, 04, 05, 09, 10
- Story cards: P1-02, 03, 04, 11 to 17, 19
- ADR-0002, ADR-0003
