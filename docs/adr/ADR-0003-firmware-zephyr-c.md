# ADR-0003: Firmware framework, language, structure and test tooling

- Status: Confirmed by the tech lead on 17 Nov 2026; becomes Accepted when one collaborator other than the author approves the PR (the EE reviews the safety-related points). Not yet pushed to GitHub.
- Date: 30 Oct 2026, amended 2 Nov 2026 for the communications structure of ADR-0004
- Story: P1-00 (issue S-002)
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0002 (controller board: NXP FRDM-MCXN947, with the EE's field-interface designs); the communications structure is in ADR-0004
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

The Phase 1 firmware reads six PT100 channels (MAX31865, SPI), two 4-20 mA channels (AD4111, SPI) and 16 optocoupler status inputs, turns them into engineering values with quality flags, and sends them to the cloud as compact records, over Ethernet or through the ESP32 over Wi-Fi and 4G (ADR-0004). Repository rules require unit tests with at least 80% line coverage and a `firmware/ci.sh` that writes a Cobertura `coverage.xml`. Developers use Windows. Only GamitPrince writes firmware.

## Decisions

1. **Operating model:** the firmware runs on an RTOS, with separate tasks for sensor reading, network communication and watchdog supervision. A simple loop with no RTOS was rejected because Phase 2 adds control loops, interlock timing and waveform processing, which would force a rewrite.
2. **RTOS:** Zephyr. FreeRTOS with NXP's MCUXpresso SDK is the fallback if the early hardware check (see below) fails. Rust/Embassy and ThreadX were not chosen (no confirmed MCX N947 support).
3. **Version:** Zephyr 4.5.0 (released 28 Oct 2026, supported until 28 Oct 2027), pinned through a `west.yml` manifest. Move to a patch release when one appears, and plan a move to the next long-term release once one is announced. Zephyr 3.7 (the current long-term release, supported until Jul 2029) was not chosen because its support for this board's features (Ethernet, ADC, MCUboot) is unconfirmed. Zephyr 4.4.0 was not chosen because its support ends in Apr 2027.
4. **Language:** C (C11). C++ and Rust were not chosen.
5. **Tests:** Zephyr's ztest framework, run by Twister on the `native_sim` host target. Coverage is measured with gcovr and reported as Cobertura `coverage.xml` by `firmware/ci.sh`.
6. **Developer environment:** WSL2 (Ubuntu) on Windows for all firmware builds and tests, because `native_sim` needs Linux. CI runs on Ubuntu, so local and CI results match.
7. **Code checks on every PR:** compiler warnings treated as errors, clang-format for style and cppcheck for static analysis, all run from `firmware/ci.sh`. MISRA C checking is not required in Phase 1 (no control or safety function in software) and is revisited in Phase 2.
8. **Structure:** four layers.
   - Hardware layer: reads raw values from the MAX31865, AD4111 and digital inputs, with no decisions.
   - Measurement layer: pure C that converts raw values to engineering units (level, temperature), checks limits and sets quality flags (open, shorted, out of range). Volume and mass are not calculated on the device (ADR-0004).
   - Record layer: builds the CBOR records from the signal list.
   - Communications layer: keeps the flash log, sends records over Ethernet or hands them to the ESP32, tracks delivery confirmations, switches paths and keeps the time (ADR-0004).
   Code that reads the safety status inputs lives in `firmware/src/safety/` and does nothing except read inputs. That folder requires the EE's approval (CODEOWNERS). The controller is send-only in Phase 1: no command changes any output, and no configuration is accepted from the cloud (firmware update and time are covered in the security ADR).
9. **AD4111 driver:** a small SPI module of our own in the hardware layer, using Zephyr's SPI interface, configuring two current channels, reading them and reporting faults. Zephyr's AD4114 binding and driver are a reference. Switch to adapting the Zephyr driver if it turns out to cover the AD4111 with little change. Time-boxed within P1-04.
10. **Coverage scope:** the 80% line coverage gate applies to all of our firmware code, including the hardware layer. Excluded from the measurement are only Zephyr itself, third-party code and generated code. Any change to the exclusion list needs the review of all three developers. To cover the hardware layer on a laptop, simulated chips (for example a fake AD4111 and MAX31865 on a fake SPI bus returning scripted register values) are used on `native_sim`. Bench tests on the real board are still performed and recorded (P1-04, P1-25), because simulations can hide real hardware faults.

## Consequences

- Almost all code is testable without the board, and the gate covers the hardware layer too.
- Decision 10 means extra work: building simulated chips for the MAX31865, the AD4111 and the digital inputs. This affects the effort of P1-04, P1-05 and P1-06.
- The FRDM board now also carries the communications work of ADR-0004 (MQTT over TLS, the flash log, failover and time sync). Together with decision 10, this raises firmware effort well above the approved story estimates, which should be reviewed. [Confirm]
- The external flash is shared between the firmware-update slots and the data log (ADR-0004).
- Developers need WSL2 set up once; this goes in `docs/setup-guide.md` (P1-24).
- Zephyr upgrades are deliberate pull requests, and thin hardware wrappers keep them cheap.
- Several parts are ready-made (MAX31865 driver, network stack, MQTT, MCUboot update path); the AD4111 module is ours.

## To verify (early in P1-01 and P1-04)

- gcovr produces Cobertura output from the Twister `native_sim` build in CI. Zephyr's documentation does not show this.
- Six MAX31865 chips on one SPI bus with six chip selects work on this board in Zephyr.
- Zephyr's ADC/SPI and Ethernet work on the real board as needed, and MQTT over TLS runs within the board's memory next to the sensor tasks. If this check fails, the fallback is FreeRTOS with the NXP SDK.
- Flashing from WSL2 works (USB probe passthrough with usbipd-win, or flash from Windows).
- Zephyr's emulation support allows simulated SPI devices on `native_sim`.
- The AD4114 driver is in Zephyr 4.5 mainline and how close it is to the AD4111.

## Not decided here

- Security: firmware-update signing keys and device certificates (security ADR).
- Firmware framework and language of the ESP32 (needs its own ADR).
- CI tooling for the other components, and the cloud and dashboard stacks.

## References

- RSD v0.2: FR-COM-01, FR-SAF-01, NFR-01, NFR-03, NFR-05
- Zephyr releases page and release process; Zephyr board page for frdm_mcxn947; Zephyr coverage documentation; Zephyr MAX31865 and AD4130/AD4114 bindings
- ADR-0002, ADR-0004
