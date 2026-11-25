# S-045: Forward the flash log over the UART link to the ESP32 (P1-12, fourth slice)

- Story ID: S-045 (issue #92).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
`log_forwarder` (S-039) gets a real `send_fn`: each log item is encoded as a CBOR record (S-044), sent as a RECORD with stop-and-wait delivery confirmation (S-043), and reported delivered only once the ESP32 has confirmed it. A record the ESP32 has confirmed is never sent again because a later item in the same batch failed.

## Phase check
Phase 1, transmit only. Records go out; only DELIVERED is read back. **Nothing here carries a command to the plant or to the FRDM's measurement.** Nothing here touches the safety chain.

## Decisions already made
- **ADR-0004 decision 3:** the FRDM keeps the data and the buffer; an unconfirmed record stays in the flash log.
- **ADR-0004 decision 5:** stop-and-wait over the framed link (S-042, S-043).
- **ADR-0004 decision 8:** about 10 s without an ack before failover; S-043's 3 × 3 s fits inside it.
- **S-043:** DELIVERED means the ESP32 has the record with the cloud (MQTT QoS 1), not just over the UART.
- **S-044:** `tank_record_cbor_encode_item()`.

## Implementation
`firmware/src/communications/uplink.h/.c`. Standard C only, like the link modules.

- `struct tank_uplink` holds the device id, a `tank_link_sender`, an encode buffer of `TANK_RECORD_CBOR_MAX` bytes, and two injected functions:
  - `read_fn(ctx, msg, timeout_ms)`: waits up to `timeout_ms` for one decoded link frame; returns 0, `-EAGAIN` on timeout, or an error. (The UART driver glue that implements it is a later story; tests use a simulated link.)
  - `now_fn(ctx)`: milliseconds, the same clock S-043 uses.
- `tank_uplink_send(ctx, items, count)` matches `tank_log_send_fn`. For each item in order: encode it; `tank_link_sender_send()`; then read frames and `tank_link_sender_poll()` until the sender reports confirmed or `-ETIMEDOUT`. It stops at the first item that fails.
- An item that fails to encode is a programming or data error, not a link error. It returns `-EINVAL` and is counted. It is **not** skipped silently; S-045 leaves it in the log and the counter shows it, and what to do with a permanently unsendable item is an open question.
- Counters: records sent, records confirmed, link give-ups, encode failures.
- A build assertion that `TANK_RECORD_CBOR_MAX` is at most `TANK_LINK_PAYLOAD_MAX`, so the firmware itself (not only S-044's tests) refuses to build if a record could outgrow a frame.

### Partial batches (change to `log_forwarder`, S-039)
Today `tank_log_send_fn` returns 0 for "all acknowledged" or an error, and `log_forwarder` rewinds the whole batch on any error. Over a stop-and-wait link, items 1 and 2 may be confirmed before item 3 fails; rewinding would send 1 and 2 to the cloud again. For scans the cloud can deduplicate on boot id and seq, but a repeated gap record would count lost scans twice.

**Proposed:** `tank_log_send_fn` returns the number of items confirmed (0 to `count`), or a negative error only when none were. `log_forwarder` acks up to the `end_pos` of the last confirmed item and rewinds the rest. This changes the S-039 contract, is about 15 lines in `log_forwarder.c` and its tests, and stays inside this story. The alternative, a batch size of 1 on this path, keeps the contract but gives up batching for the UART path.

## Interfaces touched
None in `interfaces/`. `tank_log_send_fn` in `log_forwarder.h` changes as above.

## Acceptance criteria
- A batch of scans and a gap item is encoded, sent and confirmed in order, and `log_forwarder` acks the whole batch.
- A lost RECORD or a lost DELIVERED is recovered by S-043's retransmission, and the item is confirmed once.
- When the link gives up on item k of a batch, items before k are acked in the flash log and are not sent again on the next poll; item k and later are sent again.
- An item that cannot be encoded returns `-EINVAL`, is counted, and is not reported delivered.
- A `read_fn` error is returned and the batch is not reported delivered past the last confirmed item.
- The time spent on one item never exceeds `max_attempts × ack_timeout_ms` plus one read timeout, measured on the simulated clock.
- 80% line coverage on the new code; existing `log_forwarder` tests still pass after the contract change.

## Test plan
`native_sim`, new suite `firmware/tests/communications_uplink`. A real `tank_flash_log` on the simulated flash used by S-039's tests, `log_forwarder`, `uplink`, and an S-043 `link_receiver` on the far side of a simulated link that can drop, duplicate and delay frames. Cases: clean batch, lost RECORD, lost DELIVERED, give-up mid-batch then recovery on the next poll, encode failure, read error, timing bound. No bench test: the UART is not part of this story.

## Dependency
S-039, S-043 (merged), S-044.

## Out of scope
The UART driver glue that implements `read_fn` and `write_fn`. The ESP32 application and MQTT. Path failover between Ethernet and the ESP32 (ADR-0004 decision 8). More than one RECORD in flight. Cloud-side deduplication of repeated gap records.

## Decisions (tech lead, 25 Nov 2026)
- `tank_log_send_fn` reports a partial count, as proposed above. Batch size 1 on the UART path was not chosen.
- An item that cannot be encoded returns `-EINVAL`, is counted, and stays in the log. A policy for an item that can never be sent is a later story.
- The module is `firmware/src/communications/uplink`.

## PR checklist notes
Title `feat(firmware): forward the flash log over the UART link (S-045)`, branch `feature/S-045-log-forwarder-send-fn`, `Closes #92`. No `safety` label (no safety path). CHANGELOG entry under Unreleased.
