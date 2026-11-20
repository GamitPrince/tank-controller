# P1-12: Publish readings over MQTT

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3. Points: 3. Priority: Must. Component: card says gateway; **now firmware and ESP32**. Review flag: none.

## Goal
Get records from the device to the cloud broker over MQTT, outbound only.

## Phase check
Phase 1. **Publish only.** The device subscribes to nothing that could command it; the cloud never commands devices in Phase 1.

## Decisions already made
- **ADR-0004 decision 7:** MQTT over **TLS, QoS 1, per-device certificates, outbound only**. WebSocket on 443 if 8883 is blocked.
- **ADR-0004 decisions 3, 4, 5, 6:** the ESP32 is the comms helper; the FRDM keeps the data and the buffer; the link between them is UART with our own framed protocol (COBS, sequence numbers, CRC, delivery confirmation); records are CBOR against the CDDL schema.
- **ADR-0005:** per-device key made on the board and never leaves it; our own private CA; the ESP32 has its own certificate from the same CA; each device publishes **only to its own topic**.
- **ADR-0007:** AWS IoT Core is the broker, using our CA.
- **ADR-0006:** ESP-IDF, C, Unity tests; thin TLS and MQTT wrappers are excluded from the 80% gate and covered by recorded bench tests.

## Component change
The card assigns this to `gateway/`, which ADR-0004 removed. The work now splits across the FRDM firmware (record building, buffering, delivery confirmation) and the ESP32 firmware (TLS, MQTT, link selection). **Where the ESP32 firmware lives in the repo is undecided** (`AGENTS.md` section 6) — settle that before starting.

## Acceptance criteria (from the story card)
- Each message carries value, unit, quality flag and timestamp. Unit and scale come from the signal list (P1-03); timestamps follow ADR-0004 decision 11, including the "time not yet known" flag and boot ID.
- The client reconnects automatically after a broker restart.
- Plus, from the ADRs: TLS with per-device certificate, QoS 1, publishes only to its own topic, no inbound subscription that can command the device.

## Test plan
Simulator plus a local broker: normal publish, broker restart, certificate rejected, 8883 blocked so WebSocket 443 is used, QoS 1 duplicate handling. Bench test on real hardware recorded with P1-25.

## Dependency
P1-03 (signal list and CDDL), P1-02 (simulator), the ESP32 story that does not yet exist, and **the ADR-0007 three gates before any cloud account exists**. A local broker can stand in meanwhile.

## Out of scope
Cloud-side ingest and storage (P1-17). Buffering through outages (P1-14). Certificate issuing and the CA, which have no story yet — see the index.

## Open questions
- `[Confirm]` Where does the ESP32 firmware live?
- `[Confirm]` Topic layout and batching interval — both undecided in `AGENTS.md` section 6.
- `[Confirm]` Does this story cover the FRDM side, the ESP32 side, or both? It is likely more than 300 changed lines as one PR.
