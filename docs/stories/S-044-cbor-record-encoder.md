# S-044: Encode scan and gap records as CBOR on the FRDM (P1-12, third slice)

- Story ID: S-044 (issue #91).
- Epic: E3. Points: 2. Priority: Must. Component: FRDM firmware. Review flag: none (not a safety path).

## Goal
A scan or gap item read back from the flash log becomes the exact CBOR record that `interfaces/records.cddl` describes, ready to be the payload of a RECORD frame. A scan that the schema would reject is refused, not sent.

## Phase check
Phase 1, transmit only. This story turns stored data into bytes; it sends nothing and adds no record type. **No record carries a command.** Nothing here touches the safety chain.

## Decisions already made
- **ADR-0004 decision 6:** records are CBOR, described by the CDDL schema in `interfaces/`.
- **ADR-0004 decision 9 and 11:** signals by numeric id, one timestamp per scan, boot id plus "time not yet known" flag.
- **ADR-0008:** every value carries a quality flag and an age; a fault or unconfigured reading has no value.
- **S-040:** the gap record and `struct tank_log_gap`.
- **S-039:** `struct tank_scan` and `struct tank_log_item` in `firmware/src/record/`.
- **S-042:** `TANK_LINK_PAYLOAD_MAX` = 1024 bytes per RECORD frame.
- **ADR-0003:** C11, ztest on `native_sim`, 80% line coverage, `-Werror`, clang-format.

## Scope split (decided 25 Nov 2026)
The tech lead asked for the encoder and the `log_forwarder` `send_fn` as S-044. Together they come to about 600 to 700 changed lines, over the 300-line PR limit, and one issue closes one PR. **This story is the encoder only.** The `send_fn` is S-045 (`docs/stories/S-045-log-forwarder-send-fn.md`).

## Implementation
`firmware/src/record/record_cbor.h/.c`. No CBOR library and no Zephyr API calls. (It includes `flash_log.h` for the item and gap types, and that header pulls in `<zephyr/device.h>`; the ESP32 never encodes records, so this does not matter.) The record needs only unsigned and negative integers, text and byte strings, arrays, maps and booleans, which is a small amount of code. `[Confirm]` `record/` is the right layer (it builds records; it does not send them).

- `tank_record_cbor_encode_scan(dev_id, scan, buf, cap)` writes a `record` and returns its length, or 0 if the scan is invalid or `cap` is too small.
- `tank_record_cbor_encode_gap(dev_id, gap, buf, cap)` writes a `gap-record` the same way.
- `tank_record_cbor_encode_item(dev_id, item, buf, cap)` picks one of the two by `item->kind`, so S-045 needs one call.
- **Deterministic encoding** (RFC 8949 section 4.2.1): definite lengths, shortest-form integers, map keys in core deterministic order. The same scan always gives the same bytes, so tests can compare bytes, and the cloud may hash a record if it ever needs to.
- **Validation** (return 0, write nothing useful): `count` of 0 (`r: [+ reading]` needs at least one), a quality code above 4, a reading with a value whose quality is fault or unconfigured, a device id that is empty or too long, a gap with `lost` of 0.
- `t` is written only when `tk` is true, for scans and for both gap marks.
- `val` is written only when `has_val` is true. **Digital signals are sent as the integers 0 and 1, not as CBOR booleans** `[Confirm]`: `struct tank_scan_reading` holds an `int32_t` and does not know the signal's unit, and the schema accepts `int / bool`. The simulator currently sends Python booleans for these; both decode to the same thing in the cloud.
- `v` is the constant 1 from the schema. `dev` comes from the caller.

### Size bound
- `TANK_RECORD_DEV_ID_MAX` = **32 bytes** `[Confirm]`. The schema allows up to 64; the firmware limits itself to 32 so that a worst-case scan fits in one RECORD frame. ADR-0005 has not fixed the device id format, so 32 is a firmware choice to revisit when it does.
- Worst case with 32 readings (`TANK_SCAN_MAX_READINGS`), a 32-byte device id, the time known and every integer at its widest is 1004 bytes. `TANK_RECORD_CBOR_MAX` holds the computed bound, and a build assertion checks it is at most `TANK_LINK_PAYLOAD_MAX`, so a later change to either side breaks the build instead of a send. The assertion sits in the test suite for now, because `record/` should not include a `communications/` header; S-045's `uplink.c` repeats it in the firmware itself.

Not wired into a running app, like every module so far.

## Interfaces touched
None changed. The encoder implements `interfaces/records.cddl` version 1 as merged.

## Acceptance criteria
- A scan with time known, a scan without time, a scan with a fault reading (no `val`) and a gap record each encode to the expected bytes.
- The expected bytes in the tests were produced by Python `cbor2.dumps(..., canonical=True)` from the same values and checked against `records.cddl` with the simulator's schema code; the test file states the command used.
- `t` is absent when `tk` is false, in scans and in both gap marks.
- Each invalid input listed under Validation returns 0.
- A `cap` one byte too small returns 0, for every size of record in the tests.
- Encoding the same scan twice gives identical bytes.
- A worst-case scan fits in `TANK_RECORD_CBOR_MAX`, and the static assert against `TANK_LINK_PAYLOAD_MAX` holds.
- 80% line coverage on the new code.

## Test plan
`native_sim`, new suite `firmware/tests/record_cbor`. Golden-byte cases above, integer boundary values (23, 24, 255, 256, 65535, 65536, 2^32 minus 1, negative values for `val`), every validation failure, every too-small `cap`, and the worst-case size. No bench test.

## Dependency
S-039 (scan struct, log item), S-040 (gap), S-042 (payload limit). All merged.

## Out of scope
The `log_forwarder` `send_fn` (S-045). Decoding CBOR on the FRDM. Batching several records into one frame. Link-status and time payloads. The ESP32 and MQTT. Any change to `records.cddl`.

## Open questions
- `[Confirm]` Digital values as integers 0 and 1 rather than CBOR booleans.
- `[Confirm]` Device id limited to 32 bytes in firmware until ADR-0005 fixes its format.
- `[Confirm]` `record_cbor` lives in `firmware/src/record/`.

## PR checklist notes
Title `feat(firmware): encode scan and gap records as CBOR (S-044)`, branch `feature/S-044-cbor-record-encoder`, `Closes #91`. No `safety` label (no safety path). CHANGELOG entry under Unreleased.
