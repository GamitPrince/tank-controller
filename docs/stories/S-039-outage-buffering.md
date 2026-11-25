# S-039: Buffer data locally during a link outage and forward it with original timestamps (P1-14)

- Story ID: S-039 (issue #81).
- Epic: E3. Points: 5. Priority: Must. Component: card says gateway; **now FRDM firmware**. Review flag: none.

## Goal
No data is lost when the link drops, and recovered data keeps the time it was measured.

## Phase check
Phase 1, read and store only.

## Decisions already made
- **ADR-0004 decision 3:** the **FRDM keeps the data and the buffer**, not the ESP32.
- **ADR-0004 decision 12:** a compact, lossless, **append-only flash log with delta encoding**; SD card as fallback. When full it **drops the oldest data and records a gap event**.
- **ADR-0004 decision 8:** two-tier failover, about **10 s without a cloud acknowledgement** (configurable) before switching path.
- **ADR-0004 decision 11:** SNTP plus boot-relative time with a boot ID and a "time not yet known" flag — so records buffered before the clock is known must still be placeable in time afterwards. Implemented by S-038 (`firmware/src/record/boot_time.h`).
- **ADR-0004 decision 13:** the simulator can replay an outage with original timestamps.

## Capacity calculation (done first, 2026-11-25) `[Confirm]`

Inputs: `interfaces/signals-v1.yaml` has **23 signals at 1 s** (2 loop currents, 6 PT100s, 15 contacts) and 4 health signals at 60 s. Each reading carries `id`, `val`, `q` and `age`; each record carries `boot`, `seq`, `up`, `tk`, `t` (`interfaces/records.cddl`).

| Storage form | Per 1 s scan | Per 24 h |
|---|---|---|
| Raw CBOR record as on the wire (16-char device id) | about 580 B | about 50 MB |
| Compact full snapshot (ids implicit, 16-bit values, 4-bit quality, 1-byte age, header and CRC; device and boot id once per boot) | about 70 B | about 6 MB |
| Delta against the previous scan, full snapshot every 60 s (typical: analogue noise of a few counts, contacts and quality steady) | about 17 B | about **1.5 MB** |
| Delta, worst case (every value and quality changing every scan) | about 70 B | about **6 MB** |

Health signals add about 0.25 MB per day in any form.

Flash available: Zephyr's `frdm_mcxn947` board layout puts MCUboot (80 KB) and both firmware-update slots (984 KB each) in the **2 MB internal flash**, and the whole **8 MB external W25Q64** (4 KB erase sectors) is the `storage_partition`. Allowing a reserve for other storage users and one spare sector for the ring, about **7.5 MB** is usable for the log.

**Measured, 2026-11-25:** the 24-hour test below (23 signals, a few counts of noise on every analogue reading each second, contacts toggling hourly, a sensor fault, a power cycle and an SNTP sync part-way) used **2.03 MB** of log for the day, framing and periodic full scans included. That is above the 1.5 MB estimate in the table because each entry also carries a 5-byte frame (type, length, CRC-16), but well inside the budget.

Result: 24 h fits **without the SD card** — about 3.5 days at the measured rate and about 1.2 days in the worst case. Flash wear is negligible (each sector erased roughly every 1 to 5 days, against about 100,000 erase cycles for NOR flash). ADR-0004's "about 8 MB shared with the firmware slots" is pessimistic for the default layout; if the firmware image ever outgrows a 984 KB internal slot and the slots move to external flash, this must be redone.

Assumptions: the firmware slots stay in internal flash (**decided**, see below); the pilot board carries the standard W25Q64, not the NAND rework option in the board files (`[Confirm]` with the EE); the typical delta size is measured on generated data and still to be confirmed on real plant data (ADR-0004 "To verify").

## Resolved by the tech lead, 2026-11-25
- **Capacity: accepted, no SD card** for Phase 1, on the assumptions above.
- **Buffer length: the whole log partition.** When full, the oldest sector is erased and a **gap event** is recorded, as ADR-0004 decision 12 already says. 24 h at the worst-case rate is the tested minimum.
- **Always log first.** Every record is appended to the flash log when it is made, forwarded from the log, and marked sent when the cloud acknowledges it. There is **no buffer-start threshold**: the 10 s threshold of decision 8 only decides when to switch paths. A power cut in the first seconds of an outage therefore loses nothing.
- **Test scope: native_sim with injected fakes.** The log is written through Zephyr's flash API (the flash simulator on `native_sim`), and the sender is injected as a function pointer, as S-038 did for SNTP. A bench test on the real W25Q64 is a later story.

## Resolved by the tech lead after merge, 2026-11-25 (recorded by S-040, issue #83)
- **Firmware-update slots stay in internal flash**, so **984 KB is the firmware image budget**. A CI warning when the image nears it is wanted; there is no FRDM image to measure until the firmware app exists, so it is recorded as work for P1-01.
- **The EE is to confirm** that the pilot board carries the standard W25Q64.
- **App settings:** `full_interval` **60**, `ack_persist_interval` **60** (at most about a minute of duplicates after a power cut, which P1-17 must drop), batch size **16 to 32**, the exact value chosen when the app is built.
- **Gap record:** the lost count plus the boot id, seq, up and (when known) t of the first and last lost scan, added to `interfaces/records.cddl` by S-040.

## Implementation
- `firmware/src/record/scan_codec.h/.c`: the lossless full and delta encoding of one scan. A delta entry has two bitmaps (quality, presence or age changed; value changed), so a noisy analogue reading costs one byte a scan.
- `firmware/src/record/flash_log.h/.c`: the append-only ring of 4 KB sectors over Zephyr's flash API. Entries are framed with type, length and CRC-16 and only written to erased flash; every sector starts with its own header (sequence number and delivered position) and then a full scan, so dropping a sector never orphans deltas. Mounting finds the newest sector, skips a torn entry left by a power cut and writes on in a fresh sector. When the ring is full the oldest sector is erased and a gap entry with the number of undelivered scans lost is written (a dropped sector's own gap counts are carried forward). The delivered position is persisted every `ack_persist_interval` acknowledgements; anything acknowledged after the last persisted one is resent after a power cut, and the cloud drops the duplicates (P1-17).
- `firmware/src/communications/log_forwarder.h/.c`: reads up to one batch from the log, hands it to an injected `send_fn`, and marks it delivered only when `send_fn` reports the cloud's acknowledgement; otherwise it rewinds so the batch is resent.
- Not wired into a running app (no firmware app exists yet, as for every module so far). `full_interval`, `ack_persist_interval`, the batch size and the partition are the app's configuration; the values are decided below.
- A gap reaches `send_fn` as a gap item. The gap record in `interfaces/records.cddl` that carries it to the cloud was added by S-040.

## Acceptance criteria
- A **24-hour** link outage loses no data after reconnect.
- Forwarded data keeps its **original timestamps** (`boot`, `up`, `tk`, `t` unchanged).
- Behaviour when the buffer is full is **defined and logged**: oldest dropped, gap event recorded.
- Records buffered before the clock was known keep `tk: false` and their boot id end to end.
- A power cut mid-write never corrupts records written before it (per-record checksum).

## Test plan
`native_sim`, with the flash simulator grown to 10 MB so the log gets the full 8 MB of the W25Q64. The simulator refuses to program flash that is not erased, so every test also proves the log only appends.
- `firmware/tests/record_scan_codec`: full and delta round trips keep every field; a typical noisy scan delta encodes in 20 bytes or fewer; deltas are refused across boots, signal lists or changed ids; malformed bytes and small buffers are rejected.
- `firmware/tests/record_flash_log`: read-back in order across the first SNTP sync; power cycle resumes after the last delivered scan; a torn write loses nothing written before it; a full ring drops the oldest and every scan is either kept or counted lost; ack and rewind. Forwarder: **24-hour outage** at 1 s with a power cycle at 12 h, the first boot never synced, every scan delivered afterwards in order with its original boot id, seq, up, tk and t, nothing lost; a full ring during an outage forwards a gap item; a long online run wraps a small ring many times without loss (wear is spread round robin).
- Bench test on the real W25Q64 and the simulator outage replay (P1-02) are not part of this story.

## Dependency
P1-03, P1-12, and S-038 (P1-15) for the time rules.

## Out of scope
Cloud-side duplicate suppression (P1-17). Long-term retention (ADR-0007). The real MQTT sender and the real W25Q64 bench test. SD card support.
