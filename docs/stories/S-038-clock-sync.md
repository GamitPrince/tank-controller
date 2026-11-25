# S-038: Synchronise device clocks so trends line up (P1-15)

- Story ID: S-038 (issue #79).
- Epic: E3. Points: 2. Priority: Must. Component: gateway and firmware (card); **now FRDM and ESP32 firmware**. Review flag: none.

## Goal
Every record carries a time that can be trusted and compared across devices.

## Phase check
Phase 1. Time handling only; no control implications.

## Decisions already made
- **ADR-0004 decision 11:** **SNTP** plus **boot-relative time** with a **boot ID** and a **"time not yet known" flag**. This is the whole mechanism — a device that has never reached an SNTP server still produces usable, ordered records that the cloud can place in time once a sync happens.
- **ADR-0006:** the ESP32 passes on time (SNTP) as part of its comms-helper role.
- **ADR-0008:** every value shown carries a quality flag and an age, so unsynchronised time must be visible to the dashboard, not hidden.
- **interfaces/records.cddl** already defines the record envelope this story fills in: `boot` (16-byte boot id), `up` (ms since boot), `tk` (time-known flag) and `t` (Unix seconds, present only when `tk`). This story does not change the schema, only implements what populates it.

## Resolved by the tech lead, 2026-11-23
- **Agreement limit: 1 second** — the story card's own example, well under NFR-01's 5 s freshness budget.
- **SNTP source: a public NTP pool** (`pool.ntp.org`), not the client's own network time server, so it works at any site without extra setup.
- **Who raises the Warning: the device itself**, detected locally in firmware — consistent with the controller being send-only and not dependent on cloud ingest (which is blocked by ADR-0007's gates anyway). Reported as a new health signal, **9004 `health_clock_sync_warning`**, added to `interfaces/signals-v1.yaml` alongside the existing 9001 `health_uptime` (already attributed to this story).

## Acceptance criteria
- All device clocks agree within 1 s.
- The time source is documented (a public NTP pool — see above).
- A clock error above 1 s raises the Warning (signal 9004), raised and cleared by the device itself.
- Records created before the first sync carry `tk: false` (no `t` field) and the boot id; the cloud can reconcile them once a sync happens, by matching the boot id and `up` offset.

## Implementation
- `firmware/src/record/boot_time.h/.c`: pure bookkeeping — boot id, `time_known`, the 1 s drift check, and stamping a record's `up`/`tk`/`t` fields. Takes uptime and sync results as arguments rather than reading the clock or the network itself, so it is fully unit-testable on `native_sim`.
- `firmware/src/communications/clock_sync.h/.c`: the retry policy (when to attempt a sync) and the two health signal reports (9001, 9004), built on top of `boot_time`. The actual network call is injected as a function pointer, so this is also fully unit-testable without a network stack.
- `firmware/src/communications/sntp_client.h/.c`: the real call to Zephyr's SNTP client against the public pool. **Not exercised by any test in this story** — see the `[Confirm]` note in its header: it cannot be tested on `native_sim` without a real, reachable NTP server, which would make a ztest flaky and non-deterministic. It is not referenced by any Twister test's `CMakeLists.txt`, so it is not measured by the 80% coverage gate either way; it needs bench verification (like P1-25) once there is a real network stack and app build to run it from. This mirrors ADR-0006's exclusion of thin ESP32 network wrappers from its unit-test gate, applied here by analogy since ADR-0003 does not say the same for FRDM firmware explicitly — flagged for the tech lead to confirm, not a decided exception.
- `firmware/scripts/gen_health_signals.py`: generates the health signal table (9001, 9004) from `interfaces/signals-v1.yaml`, the same pattern as `gen_level_signals.py` and `gen_equipment_status_signals.py` (ADR-0004 decision 9: ids are never hardcoded, always generated from the signal list).
- No top-level firmware app exists yet to wire these modules into a real boot sequence (same situation as every other measurement module so far) — that is the firmware-skeleton integration work, not this story.

## Test plan
`native_sim`, two ztest suites:
- `firmware/tests/record_boot_time`: normal sync, no SNTP server reachable at boot, SNTP reachable only after hours of buffering, clock step backwards during operation (drift beyond the 1 s limit raises the warning; a later sync that agrees clears it; drift within the limit never warns), boot id differing across a fresh `tank_boot_time_init` (representing a power cycle), and that no record is ever given a timestamp while `time_known` is false.
- `firmware/tests/communications_clock_sync`: the retry policy (first poll always attempts; no retry before the interval elapses; retries once it does), a fake `sync_fn` standing in for the network, and that the two health signals (9001, 9004) report the right id, quality and value.

**Not run locally in this environment**: no WSL2/Zephyr toolchain was available to build or run these on `native_sim` before pushing (tech lead, 2026-11-23, accepted this and asked to proceed on CI verification instead). CI's `firmware/ci.sh` (Twister + gcovr, runs in about 3 minutes) is the first real build/run of this code; its result on the PR should be checked before merging, not assumed.

## Dependency
Pairs with P1-14 — buffering and time are the same problem seen from two sides. Do them together or adjacently.

## Out of scope
Any use of time for control or prediction (Phases 2 and 3). The real network call's own test coverage (see "Implementation" above — bench verification, a later story). Wiring these modules into a real app boot sequence (firmware skeleton, not yet built for any story).

## Open questions
- `[Confirm]` Whether excluding `sntp_client.c` from the unit-test gate (by simply not building it in any Twister test) is acceptable here the way ADR-0006 explicitly allows it for the ESP32, or whether the tech lead wants a different treatment (e.g. a native_sim loopback NTP server) for FRDM firmware specifically.
- `[Confirm]` Whether the boot id should persist across a power cycle (e.g. in flash) rather than being freshly random each boot. This story treats it as in-memory-only per boot, matching ADR-0004 decision 11's own wording ("a boot ID ties records before/after sync together" within one boot), but flagging in case a cross-boot identifier was intended.
