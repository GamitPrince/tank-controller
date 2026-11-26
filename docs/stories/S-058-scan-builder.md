# S-058: Build the one-second scan record from the readings

- Story ID: S-058 (issue #119).
- Epic: E3 (P1-12, P1-14). Points: 2. Priority: Must. Component: FRDM firmware. Review flag: one collaborator other than the author. Not a safety path: it reads the safety contacts' status and changes nothing in `firmware/src/safety/`.

## Goal
One pure function turns the current state of the 23 Phase 1 inputs into the record the flash log stores and the uplink sends. It sets the scaled value, quality and age for each input, plus the boot-time header.

## Phase check
Phase 1, read-only. It reads module state and writes only the scan it is given. No control, no output, no write path to the safety chain.

## Where it sits
The tech lead split the firmware application into three stories on 26 Nov 2026 (one issue per PR):
1. **S-058 (this):** the scan builder, pure logic.
2. **S-059:** the 1 s scan thread. It calls the builder and appends each scan to the flash log, on a drift-free schedule.
3. **S-060:** the application `main`. It sets the boot id, mounts the flash log and starts the scan and uplink threads.

Reading the real SPI and GPIO pins waits for the EE's pin mapping. The four health signals (9001 to 9004) are a later story, decided the same day.

## Decisions already made
- **interfaces/records.cddl:** `val` is a scaled integer, absent when `q` is fault or unconfigured; every reading has a quality and an age (milliseconds from sampling to `up`).
- **interfaces/signals-v1.yaml:** loop currents have scale 0.001 mA (microamps), temperatures 0.01 degC, and digital contacts are bool, true when `value_true_means` holds.
- **ADR-0004 decision 11, S-038:** boot id, `up`, `tk` and `t` come from boot-relative time.
- **S-039:** consecutive scans delta encode only when their signal ids match, so the inputs keep a fixed order.

## Mapping
| Input | Value | Quality |
| --- | --- | --- |
| Loop current (S-034) | microamps, rounded to nearest | the module's own: good, stale, out-of-range, fault, unconfigured (never read) |
| PT100 (S-032) | centi-degC, rounded to nearest | the same |
| Contact (S-022, S-031, S-033) | 1 asserted, 0 clear | good while live; stale (last value kept) once samples stop; **fault when no state has survived the debounce yet** |

A contact's age is the time since the sample that last confirmed its state. Order in the scan: loop levels, then temperatures, then contacts, each in the order the caller gives.

## Files
- `firmware/src/record/scan_builder.h/.c`: `struct tank_scan_sources` and `tank_scan_build()`.
- `firmware/tests/record_scan_builder/`: ztest suite on `native_sim` driving the real input modules.
- `docs/features/README.md`, `CHANGELOG.md`.

## Acceptance criteria
- Good readings come out scaled, with the header (boot id, sl, seq, up, tk, t) and the right ages.
- A fault or never-read input carries no value; an unconfigured contact is a fault.
- Out-of-range and stale readings keep their value with that quality.
- A negative temperature rounds to the nearest centi-degree.
- A built scan encodes and decodes with the flash log's codec.
- NULL arguments, an array missing for its count, no inputs or more than 32 are refused.
- 80% line coverage holds.

## Test plan
`native_sim` only. No bench test: no hardware is read.

## Out of scope
The scan thread and its timing (S-059). The application, devicetree and pin reads (S-060 and later). Health signals. Averaging the ten 100 ms analogue samples into one value: the module keeps the latest sample, and a change there belongs to the acquisition story.

## Open questions [Confirm]
1. **An unconfirmed contact is a fault** (recommended, taken). The alternative is unconfigured, which is what the analogue modules report before their first reading. Fault was chosen because a safety or alarm contact in an unknown state must never look healthy. In practice it only shows if sampling never starts, since a contact confirms within 200 ms of boot.
2. **S-060 build note.** `level_switch_config.c` and `alarm_input_config.c` both include a generated header named `tank_safety_signals.h`, generated per story (P1-05, P1-09). The application cannot build both tables in one target until one of them is renamed. That rename touches `firmware/src/safety/`, so it needs the EE and the `safety` label in S-060.

## PR checklist notes
Title `feat(firmware): build the one-second scan record from the readings (S-058)`, branch `feature/S-058-scan-builder`, `Closes #119`. No `safety` label.
