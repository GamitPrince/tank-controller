# S-042: Frame messages on the FRDM-to-ESP32 UART link (P1-12, first slice)

- Story ID: S-042 (issue #87).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
Records and link messages cross the UART between the FRDM and the ESP32 as self-delimiting, checksummed frames, so a corrupted, truncated or missed frame is detected and dropped rather than delivered as data.

## Phase check
Phase 1, transmit only. The link carries records out and link status, time and delivery confirmations back. **No message type carries a command to the plant or to the FRDM's measurement, and none may be added in Phase 1.** Nothing here touches the safety chain.

## Decisions already made
- **ADR-0004 decision 4:** the FRDM-to-ESP32 link is a UART.
- **ADR-0004 decision 5:** our own small protocol: framed messages (COBS), sequence numbers, CRC and delivery confirmation, with message types "send this record", "delivered", "link status" and "time". **One small C library shared by both boards and tested on a laptop.**
- **ADR-0004 decision 3:** the FRDM keeps the data and the buffer; the ESP32 is the comms helper.
- **ADR-0003:** C11, ztest on `native_sim`, 80% line coverage, `-Werror`, clang-format.

## Scope split
P1-12 is more than one PR. This story is the **frame codec only**. Later slices, each its own story:
1. **Delivery confirmation** (next story): stop-and-wait sending with retransmit timeout and retry limit, duplicate detection on the receiving side by sequence number, and the `send_fn` for `log_forwarder` built on it.
2. Payload layouts for "link status" and "time".
3. The UART driver glue on the FRDM, and the ESP32 side (blocked on where the ESP32 firmware lives, `AGENTS.md` section 6).

## Frame format
On the wire a frame is `COBS(body)` followed by one `0x00` delimiter. COBS guarantees the body never contains `0x00`, so a receiver that joins mid-stream or loses bytes resynchronises at the next delimiter.

The body, before COBS encoding (multi-byte fields little-endian, like the flash log):

| Field | Bytes | Meaning |
| --- | --- | --- |
| version | 1 | Protocol version, `1`. A frame with another version is rejected. |
| type | 1 | Message type, below. |
| seq | 2 | Sender's sequence number, wraps at 65535. |
| payload | 0 to `TANK_LINK_PAYLOAD_MAX` | Type-specific. |
| crc | 2 | CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over version through payload. |

Message types:

| Value | Name | Direction | Payload in this story |
| --- | --- | --- | --- |
| 0x01 | RECORD | FRDM to ESP32 | Opaque bytes (CBOR record or batch, ADR-0004 decision 6). |
| 0x02 | DELIVERED | ESP32 to FRDM | 2 bytes: the seq being confirmed. |
| 0x03 | LINK_STATUS | ESP32 to FRDM | Opaque; layout is a later slice. |
| 0x04 | TIME | ESP32 to FRDM | Opaque; layout is a later slice. |

Any other type value is rejected by the decoder.

## Implementation
- `firmware/src/communications/link_frame.h/.c`: `tank_link_frame_encode()` builds header, payload and CRC, COBS-encodes and appends the delimiter into a caller buffer. `tank_link_frame_decoder` is a byte-at-a-time receiver: `tank_link_frame_decoder_push(dec, byte, &msg)` returns "frame ready", "need more", or a specific rejection (bad COBS, bad CRC, too short, too long, bad version, unknown type). After an overrun it discards bytes until the next delimiter. It keeps counters of accepted and rejected frames for later diagnostics.
- **Portability for the ESP32:** the module uses only the C standard library, with its own CRC-16 and COBS, and no Zephyr headers, so the same two files can build under ESP-IDF. `[Confirm]` It lives in `firmware/src/communications/` until the ESP32 firmware's location is decided; moving it to a shared folder then is a pure move.
- `TANK_LINK_PAYLOAD_MAX` = **1024 bytes** `[Confirm]`: enough for a catch-up batch of delta-encoded scans. Revisit with the batching interval (`AGENTS.md` section 6).
- Not wired into a running app or a UART yet, like every module so far.

## Interfaces touched
None in `interfaces/`. The frame format above is internal to the two boards. `[Confirm]` If the tech lead wants it versioned beside the CDDL schema, that is a docs move in a later story.

## Acceptance criteria
- Every message type round-trips through encode and decode with type, seq and payload unchanged, including empty and maximum-size payloads and payloads full of `0x00` bytes.
- An encoded frame contains no `0x00` except the final delimiter.
- A single flipped bit anywhere in a frame is rejected (CRC or COBS), never delivered.
- A truncated frame, a frame over the maximum size, a wrong version and an unknown type are each rejected with their own reason, and the decoder then receives the next good frame correctly.
- A receiver started mid-frame drops the partial frame and decodes the next one.
- Encoding into a buffer that is too small fails cleanly without writing past it.
- 80% line coverage on the new code.

## Test plan
`native_sim`, new suite `firmware/tests/communications_link_frame`: round trips per type and size, a COBS known-answer vector, a CRC-16/CCITT-FALSE known-answer (`"123456789"` gives `0x29B1`), every-bit-flip sweep over one frame, truncation, overrun and resync, mid-stream start, back-to-back frames in one byte stream, small output buffer. No bench test: the UART is not part of this story.

## Dependency
None blocking. P1-03 (records) and S-039 (`log_forwarder`) are merged.

## Out of scope
Retransmission, timeouts and duplicate handling (next slice). Link-status and time payload layouts. The UART driver. The ESP32 side. MQTT and TLS (rest of P1-12).

## Open questions
- `[Confirm]` Where the shared library lives once the ESP32 firmware has a home.
- `[Confirm]` `TANK_LINK_PAYLOAD_MAX` of 1024 bytes.
- `[Confirm]` UART baud rate: needed only by the UART glue slice, not here.

## PR checklist notes
Title `feat(firmware): frame messages on the FRDM-to-ESP32 UART link (S-042)`, branch `feature/S-042-uart-link-framing`, `Closes #87`. No `safety` label (no safety path). CHANGELOG entry under Unreleased.
