# P1-14: Buffer data locally during a link outage and forward it with original timestamps

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3. Points: 5. Priority: Must. Component: card says gateway; **now FRDM firmware**. Review flag: none.

## Goal
No data is lost when the link drops, and recovered data keeps the time it was measured.

## Phase check
Phase 1, read and store only.

## Decisions already made
- **ADR-0004 decision 3:** the **FRDM keeps the data and the buffer**, not the ESP32.
- **ADR-0004 decision 12:** a compact, lossless, **append-only flash log with delta encoding**; SD card as fallback.
- **ADR-0004 decision 8:** two-tier failover, about **10 s without a cloud acknowledgement** (configurable) before switching path.
- **ADR-0004 decision 11:** SNTP plus boot-relative time with a boot ID and a "time not yet known" flag — so records buffered before the clock is known must still be placeable in time afterwards.
- **ADR-0004 decision 13:** the simulator can replay an outage with original timestamps, which is how this is tested.

## Acceptance criteria (from the story card)
- A **24-hour** link outage loses no data after reconnect.
- Forwarded data keeps its **original timestamps**.
- Behaviour when the buffer is full is **defined and logged** `[Confirm buffer length]`.
- Plus: records buffered before the clock was known are reconciled using the boot ID, and the "time not yet known" flag is honoured end to end.

## Test plan
Simulator outage replay (P1-02) plus `native_sim`: 24-hour outage at the Phase 1 scan rate, buffer full, power cycle mid-outage (does the append-only log survive?), outage that begins before the first SNTP sync, flash wear over a long run.

**Capacity question to answer first, not assume:** 24 hours at 1 s per NFR-01 across every Phase 1 signal is a large number of records. Whether that fits the FRDM's flash with delta encoding, or forces the SD card fallback, is an engineering calculation this story must do early. If it does not fit, the 24-hour criterion or the scan rate has to change — that is a tech lead decision.

## Dependency
P1-03, P1-12, and ideally P1-15 for the time rules.

## Out of scope
Cloud-side duplicate suppression (P1-17). Long-term retention (ADR-0007).

## Open questions
- `[Confirm]` Buffer length target, and what happens when it is full: oldest dropped, newest dropped, or reduced rate?
- `[Confirm]` Does 24 hours of Phase 1 data at 1 s fit internal flash, or is the SD card required for the pilot?
- `[Confirm]` Is the 10 s failover threshold the same as the buffer-start threshold?
