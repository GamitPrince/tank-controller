# S-063: Pack up to five records into one link frame

- Story ID: S-063 (issue #129).
- Epic: E3 (P1-12). Points: 3. Priority: Must. Component: FRDM firmware and the shared link library. Review flag: one collaborator other than the author. Not a safety path.

## Goal
In steady state the FRDM sends one frame of five one-second records every 5 s, and one DELIVERED confirms the whole frame. The ESP32 then publishes that frame as one MQTT message (S-064). A backlog after an outage drains frame after frame.

## Phase check
Phase 1, transmit only. The frame carries the S-062 batch; nothing new is read back except DELIVERED.

## Decisions already made
- **Tech lead, 26 Nov 2026 (S-053 item 6):** five one-second records per message every 5 s, backlog oldest first, sequence numbers and confirmation kept.
- **Tech lead, 26 Nov 2026 (this session, S-062):** the FRDM packs up to five records into one frame, because the link is stop-and-wait and the ESP32 confirms only after the cloud acknowledges.
- **S-062:** `batch = [1*5 message]`, complete records, oldest first.
- **ADR-0004 decision 3:** the FRDM keeps the buffer; a frame that is not confirmed stays in the flash log.

## Implementation
1. **Frame size** (`shared/link-protocol/link_frame.h`): `TANK_LINK_PAYLOAD_MAX` rises from 1,024 to 5,120 bytes. That is room for five worst-case records (about 1,004 bytes each, `record_cbor.h`) and the array header. Frame buffers on both boards grow to about 5 KB each, which both have room for. Two test suites that keep frames on the stack get a 16 KB test stack.
2. **Uplink** (`firmware/src/communications/uplink.h/.c`): `tank_uplink_send()` packs up to `TANK_UPLINK_BATCH_MAX` (5) leading items, oldest first, into one frame as a CBOR array, then waits for that frame's DELIVERED.
   - Several frames go one after another when given more items.
   - The count returned is the number of items in confirmed frames, so `log_forwarder` acks whole frames.
   - A frame stops at the first item that cannot be encoded. When that is the first item, `-EINVAL` is returned, as before.
   - `sent` and `confirmed` now count frames.
   - A static assert keeps a full batch inside one frame.
3. **Uplink service** (`uplink_service.h/.c`): a new `full_batch` setting.
   - A poll that delivered at least that many polls again at once, because more may be waiting.
   - A poll that delivered fewer, or none, means caught up, so the service waits `idle_ms` and the next batch fills.
   - 0 keeps the S-049 behaviour.
4. **Application:**
   - The forwarder reads `TANK_UPLINK_BATCH_MAX` items per poll, one frame's worth, instead of 16.
   - `main.c` polls every 5 s when caught up (was 1 s in S-049, superseded by the 5 s batch interval), with `full_batch` = 5.
   - The 5 s retry is unchanged.

## Interfaces touched
None in `interfaces/`; the frame carries the S-062 batch. The link frame format is unchanged; only its size limit grows.

## Acceptance criteria
- Five scans go in one frame, which the ESP32 confirms once. Seven scans go in a frame of five, then a frame of two, oldest first. Each frame's bytes are exactly the batch the scans encode to.
- If the link dies on the second frame, the first frame's items stay acked, and only the rest are sent again.
- A lost frame or a lost DELIVERED is recovered and passed up once.
- An item that cannot be encoded ends its frame, and the next send refuses it.
- Over the emulated UART, five scans arrive as one frame and one DELIVERED comes back.
- A part batch counts as caught up: the service waits `idle_ms`.
- All existing suites pass, and 80% line coverage holds.

## Test plan
`native_sim`: `communications_uplink` (frames checked by length and CRC against the encoded batch), `hardware_esp32_uart` end to end, `communications_uplink_service`, `app_tank_app`, the link suites. ESP32 host tests run unchanged against the larger frame.

## Out of scope
- **ESP32 publishing** the frame as one MQTT message (S-064).
- **Sending at once on a change** (below).
- **The simulator emitting batches.**

## Open questions [Confirm]
1. **NFR-01, send at once on a change.** With a 5 s poll, a contact change or a quality change can wait up to about 5 s at the FRDM before it is sent, which strains NFR-01's 5 s end-to-end target. Recommended next story: the scan service wakes the uplink at once when any contact's value or any reading's quality changes, so alarms are not batched behind the timer.

## PR checklist notes
Title `feat(firmware): pack up to five records into one link frame (S-063)`, branch `feature/S-063-pack-records-per-frame`, `Closes #129`. No `safety` label.
