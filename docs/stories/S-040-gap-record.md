# S-040: Tell the cloud about scans lost to a full outage buffer (gap record)

- Story ID: S-040 (issue #83). Follow-up to S-039 (P1-14, issue #81).
- Component: interfaces, firmware, simulator. Review flag: **one approval from a collaborator other than the author** (`interfaces/` changes, S-010). No EE review: nothing under `firmware/src/safety/`.

## Goal
When the outage buffer is full and drops data that was never delivered, the cloud is told exactly which scans are missing, so a trend shows a marked hole rather than a silent one.

## Phase check
Phase 1, send-only. The gap record is one more message from the device; nothing flows to the device.

## Decisions already made
- **ADR-0004 decision 12:** when full, the log drops the oldest data and records a gap event (S-039).
- **ADR-0004 decision 6:** records are CBOR described by `interfaces/records.cddl`.
- **ADR-0008 and AGENTS.md section 7:** stale or missing data is never shown as live, and a screen must not imply data that is not there.

## Resolved by the tech lead, 2026-11-25
- **Gap record content:** the number of scans lost plus the boot id, seq, up and (when known) t of the **first and last lost scan**, so the dashboard can mark exactly where the hole is.
- The follow-up decisions on S-039 (firmware slots, the 984 KB budget, the EE check of the flash chip, and the app settings 60 / 60 / 16 to 32) are recorded in `docs/stories/S-039-outage-buffering.md`, and the size warning in `docs/stories/P1-01-repo-and-ci-skeleton.md`.

## Interfaces touched
`interfaces/records.cddl`: the root becomes `record / gap-record`. A gap record is `{v: 1, dev, gap: {lost, first, last}}`, where `first` and `last` are `lost-scan = {boot, seq, up, tk, ? t}`. The two record types are told apart by their keys (`r` against `gap`). `v` stays 1: no device or cloud consumes the schema yet, so this is an addition, not an incompatible change.

Every scan from `first` to `last` was dropped. Each dropped scan is counted in exactly one gap record, but the ranges of two gap records may overlap, because a gap carried forward keeps its original `first` while a newer gap may already cover part of that range.

## Implementation
- `firmware/src/record/flash_log.h/.c`: a gap entry now holds the lost count and the first and last lost scan. To find them, dropping a sector decodes its scans (every sector starts with a full scan). An older undelivered gap in the dropped sector widens the new gap's range and adds to its count. The forwarder's gap item carries a `struct tank_log_gap`.
- `firmware/src/record/scan_codec.h/.c`: a delta may be decoded in place (`out == prev`), which saves a second 600-byte scan buffer when dropping a sector.
- `simulator/tanksim/cddl.py`: when a value matches no alternative of a choice, the error now says why each alternative failed, so a bad scan record still gets a precise message now that the root is a choice.
- How the MQTT sender (P1-12) encodes the gap item as a gap record is P1-12's work; this story defines the record and makes the firmware hold everything it needs.

## Acceptance criteria
- A scan record and a gap record both validate against the root rule; a malformed gap record, or one mixing scan and gap keys, does not.
- The firmware's gap items place the hole exactly: across all gap items, the oldest `first` is the oldest dropped scan and the newest `last` is the scan just before the oldest kept one, even after gaps were carried forward.
- Every scan is either delivered or counted lost exactly once.

## Test plan
- `simulator/tests/test_cddl.py`: a good gap record passes; bad count, short boot id, missing field, extra key, missing `gap`, and a mix of scan and gap keys are all rejected; every scan record rejection still gives its precise message at the root.
- `firmware/tests/record_flash_log`: the full-log test checks the gap ranges and counts as above; the forwarder tests check each gap item's range is ordered.
- `firmware/tests/record_scan_codec`: in-place delta decoding.

## Out of scope
Sending the gap record over MQTT (P1-12). Showing gaps on the dashboard (P1-21 to P1-23). The firmware size warning (recorded for P1-01). The simulator producing gap records: its own buffer never drops data.

## Open questions
- Resolved 2026-11-25 (S-041, issue #85): the pilot board carries the standard Winbond W25Q64JV, confirmed from the tech lead's photos of the board.
