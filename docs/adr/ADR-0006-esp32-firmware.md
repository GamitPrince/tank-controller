# ADR-0006: ESP32 communications firmware: framework, language, tests, lock and modem

- Status: **Accepted.** Confirmed by the tech lead on 17 Nov 2026; approved by prinz-assists, a collaborator other than the author, and merged on 20 Nov 2026 in PR #14.
- Date: 17 Nov 2026
- Story: P1-00 (issue S-002); shapes a new ESP32 firmware story (to be created)
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0002 (hardware), ADR-0003 (FRDM firmware), ADR-0004 (communications), ADR-0005 (security)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

ADR-0004 makes the ESP32-S3 + A7672S board (K-tron listing, specifications not yet verified) a communications helper in the same panel as the FRDM. It gets records from the FRDM over a UART with our own framed protocol, and sends them to the cloud over MQTT over TLS using Wi-Fi, with 4G as backup. It switches between Wi-Fi and 4G on its own, reports link state, passes on time (SNTP), and reports delivery. ADR-0005 gives it its own certificate and requires signed boot, a locked debug port on site units, and outbound-only connections. It is a second firmware that needs a framework, a language, a test approach, a lock procedure and a way to use the 4G modem. Repository rules require unit tests with at least 80% line coverage and a `ci.sh` that writes a Cobertura `coverage.xml`. Only GamitPrince writes firmware.

## Decisions

1. **Framework:** ESP-IDF (Espressif's official framework, built on FreeRTOS). Zephyr on the ESP32 would give one toolchain for both boards, but its Wi-Fi, modem and secure-boot support is, to our understanding, less proven on the ESP32. Arduino was not chosen because it gives less control over security and updates. [To verify: the ESP-IDF version to pin, and the board's chip variant and flash size]
2. **Language:** C. The shared link-protocol library of ADR-0004 is written once in C and compiled for both boards. C++ and Rust were not chosen.
3. **Tests:** Unity (the test tool that comes with ESP-IDF), run as plain C programs on a laptop and in CI, with coverage measured by gcovr and written as Cobertura `coverage.xml` by the ESP32 component's `ci.sh`. The code is split into logic (link protocol, failover decisions, send queue, record handling), which is chip-independent, and thin wrappers over ESP-IDF's Wi-Fi, modem, TLS and MQTT. The 80% gate counts our logic. The wrappers are excluded from the measurement and are covered by recorded bench tests (with P1-25). The exclusion list needs the review of all three developers. Counting the wrappers with simulated Wi-Fi, modem and MQTT (as for the FRDM in ADR-0003 decision 10) was not chosen, because it would be a lot of extra work for code that mostly forwards calls.
4. **Secure boot and flash encryption:** secure boot and flash encryption are enabled on units that go to a client site, in line with ADR-0005 decision 8. Development boards stay open. The ESP32 has its own firmware signing key, separate from the FRDM's key and from the CA key, stored and protected the same way as in ADR-0005 decision 4 (pipeline secret with its four safeguards). The permanent chip settings (eFuses) are a release step with a written bench procedure, tried first on a spare board, because a mistake can make a unit unusable. Signed updates with rollback are enabled. Signed updates only, without the chip lock, were not chosen.
5. **4G modem:** the A7672S is used as a network connection over PPP, so the same TLS and MQTT code runs on Wi-Fi and 4G, and the certificate and private key stay in the ESP32 (ADR-0005). If ESP-IDF's modem component does not support the A7672S, we write a small adapter or workaround. The modem's built-in MQTT and TLS over AT commands was not chosen, because it would put keys in the modem and make the two paths behave differently.

## Consequences

- A second toolchain (ESP-IDF) next to Zephyr, a second CI job and a second `ci.sh` that writes `coverage.xml`. Developers need ESP-IDF set up once; this goes in `docs/setup-guide.md` (P1-24).
- A new story card is needed for the ESP32 firmware (link, Wi-Fi, 4G, failover, TLS and MQTT, time, delivery reports, update), and one for the bench tests of the wrappers. Estimates need review. [Confirm]
- The wrappers are not covered by the 80% gate, so bench tests matter: Wi-Fi and 4G connection, failover, MQTT over TLS, reconnect and the delivery path must each have a recorded bench test.
- The ESP32 holds a private key and handles all data on the Wi-Fi and 4G path, so it must be locked on site units. The eFuse steps are permanent, so provisioning and release procedures must be written and rehearsed.
- The shared link library sits in a place both firmware builds can use (decided when P1-01 sets up the repository structure).

## To verify (early, in the communications spike)

- The exact ESP32 chip variant, flash size, UART pins, power input, antenna connectors and temperature rating of the K-tron board (specs not yet verified).
- ESP-IDF's modem component works with the A7672S over PPP (and the AT commands needed for SIM, registration and signal strength).
- TLS and MQTT run on the ESP32 with our own certificate on both Wi-Fi and 4G, and failover between them takes under about 10 s (ADR-0004).
- The ESP32-S3's secure boot and flash encryption options and the eFuse steps, tried on a spare board; where the device key is created and kept (ADR-0005 decision 1 applies here too).
- Host builds of the logic with Unity and gcovr work in CI and produce a Cobertura `coverage.xml`.
- Unity tests can build the shared link library for the laptop and the target from one source.

## Not decided here

- The ESP-IDF version to pin, and the build environment on Windows (WSL2 like the FRDM, or native). [Confirm]
- How firmware updates reach the ESP32 and the FRDM (over the network from the cloud, or only by cable in Phase 1), and the update delivery design.
- The cloud and dashboard (cloud and dashboard ADRs).
- CI tooling for the other components.

## References

- RSD v0.2: FR-COM-01, FR-COM-03, FR-COM-04, NFR-05, NFR-10
- ADR-0002, ADR-0003, ADR-0004, ADR-0005
