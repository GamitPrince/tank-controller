# S-043: Confirm delivery on the FRDM-to-ESP32 UART link (P1-12, second slice)

- Story ID: S-043 (issue #89).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
A RECORD sent over the UART link is either confirmed by a matching DELIVERED, or retried and then reported as failed. A retransmitted RECORD is never forwarded twice by the receiving side. Nothing is lost silently and nothing is duplicated silently.

## Phase check
Phase 1, transmit only. This story adds no message type. RECORD still goes from the FRDM to the ESP32 and DELIVERED still comes back. **Nothing here carries a command to the plant or to the FRDM's measurement.** Nothing here touches the safety chain.

## Decisions already made
- **ADR-0004 decision 5:** our own framed protocol with sequence numbers, CRC and delivery confirmation, in one small C library shared by both boards and tested on a laptop.
- **ADR-0004 decision 3:** the FRDM keeps the data and the buffer. A RECORD that is not confirmed stays in the flash log and is resent later by `log_forwarder` (S-039), so this layer may give up without losing data.
- **ADR-0004 decision 8:** failover after about 10 s without a cloud ack. The default timeout and retry limit below fit inside that.
- **S-042:** the frame codec (`link_frame.h`), with DELIVERED carrying the confirmed seq as a 2-byte payload.
- **ADR-0003:** C11, ztest on `native_sim`, 80% line coverage, `-Werror`, clang-format.

## Scope split (decided 25 Nov 2026)
The S-042 spec put the `log_forwarder` `send_fn` into this slice. That `send_fn` needs a CBOR encoder that turns log items into records (CDDL in `interfaces/`), and none exists in the firmware yet. **This story is stop-and-wait and duplicate detection only, over opaque payloads.** The CBOR record encoder and the `send_fn` built on this story are later stories.

## Implementation
Both modules use only the C standard library and `link_frame`, with no Zephyr headers, so they can build under ESP-IDF like S-042. `[Confirm]` They live in `firmware/src/communications/` until the ESP32 firmware has a home.

### Sender: `link_sender.h/.c` (FRDM side)
- One RECORD in flight at a time (stop-and-wait).
- `tank_link_sender_send(s, payload, len, now_ms)` encodes a RECORD with the next seq and writes it through an injected `write_fn`. It returns `-EBUSY` while a RECORD is in flight.
- `tank_link_sender_on_msg(s, msg)` takes a decoded frame. A DELIVERED whose payload names the in-flight seq completes the send. A DELIVERED for any other seq (stale or unknown) is counted and ignored. Other message types are not its business and are ignored.
- `tank_link_sender_poll(s, now_ms)` resends the same frame, with the same seq and bytes, once `TANK_LINK_ACK_TIMEOUT_MS` has passed without confirmation. After `TANK_LINK_MAX_ATTEMPTS` attempts in total it gives up and reports `-ETIMEDOUT`. The caller (later, the `send_fn`) then returns an error to `log_forwarder`, which rewinds and resends later.
- Time is passed in as milliseconds, so tests run without real waiting. Elapsed time is computed with unsigned subtraction, so a wrapping clock is safe.
- The seq increments per new RECORD (not per retransmit) and wraps from 65535 to 0.
- Counters for diagnostics: sent, retransmitted, confirmed, given up, stale acks.

### Receiver: `link_receiver.h/.c` (ESP32 side, tested on `native_sim`)
- `tank_link_receiver_on_msg(r, msg, &deliver)` takes a decoded RECORD and decides whether it is new (pass it up once) or a duplicate (do not pass it up).
- **Duplicate rule:** same seq **and** same payload length and CRC-16 as the last RECORD accepted. Comparing the payload as well as the seq means a FRDM that reboots and restarts its seq is not mistaken for a retransmit. `[Confirm]` The residual risk is a fresh RECORD with the same seq, length and CRC-16 as the previous one (about 1 in 65536 after a seq restart). Accepted for Phase 1 because the cloud also deduplicates on boot id and seq (ADR-0004 decision 11).
- `tank_link_receiver_confirm(r, seq, out, cap, &len)` builds the DELIVERED frame once the upper layer (later, MQTT QoS 1 to the cloud) has the record. A duplicate of a RECORD that was already confirmed gets its DELIVERED again, so a lost DELIVERED does not stall the sender. A duplicate of one not yet confirmed is dropped without reply.
- Counters: accepted, duplicates.

### Constants
- `TANK_LINK_ACK_TIMEOUT_MS` = **3000** `[Confirm]`.
- `TANK_LINK_MAX_ATTEMPTS` = **3** `[Confirm]`. 3 × 3 s = 9 s stays inside ADR-0004 decision 8's roughly 10 s. Both are set at init from a config struct; the constants are the defaults.

Not wired into a running app or a UART yet, like every module so far.

## Interfaces touched
None in `interfaces/`. No change to the S-042 frame format.

## Acceptance criteria
- A RECORD confirmed by a matching DELIVERED completes, and the next RECORD uses the next seq.
- A lost RECORD and a lost DELIVERED are each recovered by retransmission with the same seq, and the receiver passes the record up exactly once.
- After `TANK_LINK_MAX_ATTEMPTS` attempts without confirmation, the sender reports `-ETIMEDOUT`, is free to send again, and uses a new seq.
- A DELIVERED for a stale or unknown seq does not complete the send.
- Sending while a RECORD is in flight returns `-EBUSY` and writes nothing.
- The seq wraps from 65535 to 0, and both sides keep working across the wrap.
- A RECORD with a repeated seq but a different payload (the FRDM rebooted) is accepted as new.
- A write failure from `write_fn` is returned to the caller.
- 80% line coverage on the new code.

## Test plan
`native_sim`, new suite `firmware/tests/communications_link_delivery`. Sender and receiver are joined through `link_frame` encode and decode by a simulated link that can drop, duplicate or delay frames in either direction under test control. Cases: clean delivery, lost RECORD, lost DELIVERED, duplicated RECORD, stale DELIVERED, give-up at the retry limit, busy, seq wrap, seq restart with a new payload, write failure, clock wrap. No bench test: the UART is not part of this story.

## Dependency
S-042 (frame codec), merged.

## Out of scope
The CBOR record encoder. The `log_forwarder` `send_fn`. Link-status and time payload layouts. The UART driver glue. The ESP32 application and MQTT. Path failover (ADR-0004 decision 8). More than one RECORD in flight (a window).

## Open questions
- `[Confirm]` Timeout 3000 ms and 3 attempts.
- `[Confirm]` Duplicate rule (seq plus payload length and CRC-16) and its residual risk.
- `[Confirm]` Location of the shared library once the ESP32 firmware has a home.

## PR checklist notes
Title `feat(firmware): confirm delivery on the FRDM-to-ESP32 UART link (S-043)`, branch `feature/S-043-delivery-confirmation`, `Closes #89`. No `safety` label (no safety path). CHANGELOG entry under Unreleased.
