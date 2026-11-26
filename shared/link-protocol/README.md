# shared/link-protocol

The FRDM-to-ESP32 UART link library (ADR-0004 decisions 4 and 5). Both boards compile these files, so they use only the C standard library (C11).

| File | What it does | Story |
| --- | --- | --- |
| `link_frame.h/.c` | Frames: COBS framing, version, type, sequence number, CRC-16/CCITT-FALSE; encode and a streaming decoder that resyncs after damage | S-042 |
| `link_sender.h/.c` | Stop-and-wait sender on the FRDM: resends a RECORD until its DELIVERED arrives, gives up after a set number of attempts | S-043, S-045 |
| `link_receiver.h/.c` | Duplicate-safe receiver on the ESP32: passes each RECORD up once and re-confirms a repeat | S-043 |

No message type carries a command to the plant or to the FRDM's measurement (Phase 1 is read-only), and none may be added.

## Who builds and tests it

- **FRDM firmware** (`firmware/`): the ztest suites `firmware/tests/communications_link_frame` and `communications_link_delivery` test the library itself, and `communications_uplink` and `hardware_esp32_uart` test it inside the FRDM send path. `firmware/ci.sh` formats it, runs cppcheck on it and counts it in the 80% coverage gate.
- **ESP32 firmware** (`esp32/`): `esp32/tests/` builds it on the host with Unity and tests the ESP32's `link_endpoint` against the real sender. `esp32/ci.sh` counts only `esp32/components/`, so the library is not counted twice.

A change here runs both the `firmware` and the `esp32` CI jobs. The formatting style is `firmware/.clang-format`.
