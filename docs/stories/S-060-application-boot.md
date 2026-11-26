# S-060: Boot the firmware application: inputs, log and the scan thread

- Story ID: S-060 (issue #123).
- Epic: E3 (P1-12, P1-14). Points: 3. Priority: Must. Component: FRDM firmware. **Review flag: `safety` label and the EE's approval.** One include line in `firmware/src/safety/alarm_input_config.c` changes; no safety logic changes.

## Goal
The firmware has an application. After hardware initialisation it:
- sets a fresh random boot id;
- mounts the flash log on the partition the devicetree names;
- sets up all 23 Phase 1 inputs from the signal-list tables;
- starts the S-059 scan service.

Logging starts whether or not a network is up.

## Phase check
Phase 1, read-only. No input is driven and nothing is written to the safety chain. The safety-folder change is a renamed generated header, not a behaviour change.

## Decisions already made
- **Tech lead, 26 Nov 2026:** the application is split into S-058, S-059 and S-060. The FRDM acquires and logs from boot independently of the network, and the ESP32 connects on its own. There is one record per second.
- **S-038:** the boot id is random, fresh every boot, kept in memory.
- **S-039:** `full_interval` 60 and `ack_persist_interval` 60 are the application's settings.
- **AGENTS.md section 1:** a change under `firmware/src/safety/` needs the EE and the `safety` label.

## Implementation
1. **Safety header clash (the safety-path change).**
   - **Problem:** `level_switch_config.c` (P1-05) and `alarm_input_config.c` (P1-09) both included a generated `tank_safety_signals.h` with the same include guard, generated once per story. So no single build could hold both tables.
   - **Generator:** `gen_safety_signals.py` now gives each story its own include guard.
   - **Alarm table:** it includes `tank_alarm_signals.h`, and its test generates that name.
   - **Unchanged:** the P1-05 table, the contracts, the macros and every value.
2. **`firmware/cmake/`.** `tank_signals.cmake` generates all five signal tables into one build. `tank_app_sources.cmake` lists the sources the application is built from, shared by the application and its test so they cannot drift.
3. **`firmware/src/app/tank_app.h/.c`.**
   - `tank_app_start()` sets up the inputs in scan order (2 loop levels, 6 PT100s, then 15 contacts: level switches, alarms, equipment status), starts the boot time, mounts the flash log, creates the input lock and starts the scan service with `sl` from the signal list.
   - It returns `-EALREADY` while running, so a second call cannot clear a running thread's state.
   - `tank_app_stop()` and `tank_app_sources()` are also provided.
4. **`firmware/app/`.**
   - The Zephyr application: `main.c` fills the configuration (1 s scans, 1 s clock agreement, 4 KB sectors, the S-039 intervals) and draws the boot id from `sys_rand_get()`.
   - The log partition is the devicetree's chosen `tank,log-partition`. `boards/native_sim.overlay` points it at the simulated flash's storage partition; the FRDM overlay will point it at the W25Q64.
5. **`firmware/ci.sh`.** Twister also builds `app/` (build only, native_sim), and clang-format and cppcheck cover it.

## What a record shows until acquisition exists
Nothing samples the pins yet, so every loop level and PT100 is `unconfigured` and every contact is `fault`, all without a value. A record never carries a made-up number.

## Interfaces touched
None. `interfaces/` and the generated values are unchanged.

## Acceptance criteria
- All 23 inputs are set up, in scan order, from the signal-list tables.
- Scans start with no network, carry the boot id, `sl` 1 and `tk` false, and no reading has a value.
- A running application is not restarted. A stopped one starts again.
- A NULL argument, a missing boot id, a zero clock limit, an invalid log partition and a zero scan period are each refused.
- The application builds for native_sim in CI. Every existing suite, including `safety_alarm`, passes unchanged.
- 80% line coverage holds.

## Test plan
`native_sim` with the flash simulator, new suite `firmware/tests/app_tank_app`, plus the build-only application. No bench test: no pin is read.

## Out of scope
- **Uplink wiring:** the device id source (ADR-0005 provisioning) and the ESP32 UART taken from devicetree. That is the next story.
- **Real input reads:** SPI and GPIO, waiting on the EE's pin mapping.
- **Clock sync wiring and health signals.**
- **A watchdog:** safe-state behaviour, needing its own story and the tech lead's go-ahead.

## Open questions [Confirm]
1. **`firmware/src/app/`** holds the composition layer above ADR-0003's four layers, with `firmware/app/` the Zephyr application around it. Recommended, taken.
2. **The boot id uses `sys_rand_get()`.** It needs to be unique, not secret. A secure source (`sys_csrand_get()`) can be swapped in when the FRDM's TRNG is configured.

## PR checklist notes
Title `feat(firmware): boot the application with its inputs, log and scan thread (S-060)`, branch `feature/S-060-application-boot`, `Closes #123`. **`safety` label; the EE (`@gamitriyan-del`) approves the `firmware/src/safety/` change.**
