# S-064: Publish each FRDM batch as one MQTT message

- Story ID: S-064 (issue #131).
- Epic: E3 (P1-12). Points: 2. Priority: Must. Component: ESP32 firmware. Review flag: one collaborator other than the author. Not a safety path.

## Goal
The ESP32 publishes each batch the FRDM sends as one MQTT message on `tank/{device_id}/records`. It confirms the batch to the FRDM only once the broker has acknowledged it.

## Phase check
Phase 1, transmit only. The ESP32 publishes and reads back only PUBACKs. It subscribes to nothing, and nothing commands the FRDM or the plant.

## Decisions already made
- **ADR-0004 amendment 4:** topic `tank/{device_id}/records`; five one-second records every 5 s; backlog oldest first; unacknowledged records kept and resumed after reconnect.
- **ADR-0004 decisions 3 and 7:** the FRDM keeps the buffer; MQTT over TLS at QoS 1.
- **ADR-0005 decision 6:** the ESP32's certificate is linked to the DAQ's device ID at provisioning, and each device publishes only to its own topic.
- **ADR-0006 decision 3:** Unity host tests on our logic; thin wrappers over Wi-Fi, TLS and MQTT are excluded from the gate and covered by recorded bench tests.
- **S-047:** the endpoint calls the upper layer once per new RECORD and writes DELIVERED only on confirm.
- **S-062, S-063:** a RECORD carries a batch of one to five records.

## Implementation
`esp32/components/publisher/` (standard C):
- **`tank_publisher_init(pub, cfg)`** takes the device ID, a `publish_fn` that reaches the ESP-IDF MQTT client, and the link endpoint.
  - It builds the topic `tank/<id>/records`.
  - It refuses an ID that is empty, longer than 32 characters (the record encoder's limit), or holds `/`, `+` or `#`.
- **`tank_publisher_on_record()`** is the endpoint's `record_fn`. It publishes the payload unchanged at QoS 1 and remembers the message id and the RECORD's seq.
  - A failed publish (no connection, full outbox, or a zero id) is counted and not remembered, so it is never confirmed.
  - A new RECORD while one waits means the FRDM gave up on the old one, so the old one is dropped.
- **`tank_publisher_on_puback(pub, msg_id)`** confirms the waiting RECORD through the endpoint when the id matches, and the endpoint writes DELIVERED.
  - Any other PUBACK, or a repeat, is counted as stale and confirms nothing.
- **Stats:** published, confirmed, publish errors, stale PUBACKs, last error.
- **`esp32/tests/test_publisher.c`:** the real endpoint, a fake MQTT client and a fake UART that decodes what the endpoint writes. `esp32/tests/CMakeLists.txt` builds it with coverage.

## Interfaces touched
None. The ESP32 forwards the S-062 batch byte for byte.

## Acceptance criteria
- The topic is `tank/<device id>/records`.
- A RECORD is published unchanged, and DELIVERED for its seq goes back only after its PUBACK.
- A failed publish is never confirmed, and a later PUBACK for it is stale.
- A PUBACK for another message confirms nothing; the right one still does; a repeat does nothing.
- A new RECORD replaces one the FRDM gave up on, and only the new one's PUBACK confirms.
- Bad device IDs and NULL arguments are refused.
- The ESP32 job's 80% gate holds on `esp32/components/`.

## Test plan
Unity on the host, run by `esp32/ci.sh` in the `esp32` CI job. No bench test yet: the real broker connection is the AWS IoT Core proof of concept, on the real ESP32-S3 board.

## Out of scope
- **The ESP-IDF glue.** That is the MQTT client set up with the device certificate, its published event calling `tank_publisher_on_puback()`, and the UART task feeding the endpoint. It comes with the first ESP-IDF build in CI (the S-047 spec, item 4) and the IoT Core proof of concept.
- **Wi-Fi, 4G (PPP) and failover.**
- **Provisioning the device ID and certificate.**
- **The broker policy** that limits each certificate to its own topic.

## Open questions [Confirm]
1. **What happens on reconnect.** The ESP-IDF client keeps an unacknowledged QoS 1 message in its outbox and resends it after a reconnect. If the FRDM has already given up (after about 9 s), the late PUBACK is stale, and the FRDM's resend reaches the cloud as a duplicate, which the cloud drops on boot id and seq (ADR-0004 decision 11). Recommended and taken: accept the rare duplicate rather than hold records on the ESP32.

## PR checklist notes
Title `feat(firmware): publish each FRDM batch as one MQTT message (S-064)`, branch `feature/S-064-esp32-publisher`, `Closes #131`. No `safety` label.
