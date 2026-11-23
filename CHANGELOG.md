# Changelog

All notable changes to this project are recorded here. Format follows Keep a Changelog; versions follow MAJOR.MINOR.PATCH (see the tag scheme in the GitHub Workflow Guide).

## [Unreleased]

### Added

- Repository scaffolding, CI, pull request policy and review rules.
- ADR-0003: firmware framework, language, structure and test tooling — Zephyr RTOS 4.5.0 pinned, C11, ztest and Twister on `native_sim` (#11).
- ADR-0004: communications architecture, data format and simulator — no separate gateway, own framed protocol over UART, CBOR records, MQTT over TLS, Python simulator (#12).
- ADR-0005: security design — per-device keys made on the board, own private CA, outbound-only TLS, signed boot (#13).
- ADR-0006: ESP32 communications firmware — ESP-IDF, C, Unity tests, secure boot and flash encryption on site units, A7672S over PPP (#14).
- ADR-0007: cloud architecture — managed AWS services, IoT Core as broker, Tiger Cloud for readings, with three gates before any account is opened or paid for (#15).
- ADR-0008: backend and dashboard — FastAPI backend, TypeScript and React dashboard, Amazon Cognito login, append-only audit trail, server-sent events (#16).
- ADR-0009: CI and deployment — Terraform or OpenTofu blueprints, test and live copies, OIDC login to AWS, free GitHub security set on every pull request (#17).
- `simulator/ci.sh` and `firmware/ci.sh`, the first component CI scripts, so the 80% line-coverage gate measures real code instead of passing on empty folders (#32). The simulator gets the `tanksim` Python package with pytest and ruff; the firmware gets ADR-0003's four layers (`hardware/`, `measurement/`, `record/`, `communications/`), a C11 measurement module with a ztest suite run by Twister on `native_sim`, `west.yml` pinning Zephyr 4.5.0, and gcovr filtered to `src/` so coverage counts the hardware layer too. Both report an out-of-range reading rather than clamping it. `gateway/` deliberately gets no script: it is obsolete under ADR-0004.

- The Phase 1 signal list and CBOR record schema, the first contents of `interfaces/` (#36). `signals-v1.yaml` defines the 23 plant signals from the EE's inventory of 20 Nov 2026 — two AD4111 4-20 mA channels, six 3-wire PT100s on one MAX31865, 15 of 16 optocoupler digital channels — plus three device-health signals, each with an id, name, unit, scale, update rate and read-only flag, and each digital channel with its contact sense and debounce. It replaces the register map (ADR-0004 decision 9). The two contact senses are deliberately not harmonised: normally closed on the safety-chain and alarm channels so a broken wire reads as alarm, normally open on equipment status so open means not running. Every signal is read-only, and volume, mass and level percent are absent because the cloud computes them (decision 10). `records.cddl` describes the CBOR scan record (decision 6); it versions independently of the list, every reading carries a quality flag and an age, and a faulted reading carries no value rather than a substituted one.

- The Phase 1 simulator, a standalone Python package that produces every signal in `interfaces/signals-v1.yaml` with no hardware (#38, ADR-0004 decision 13). One command, `python -m tanksim`, runs scans that each become a CBOR record validated against `interfaces/records.cddl` and framed with COBS, a sequence number and a CRC. The signal list and the schema are loaded at runtime, so no id, scale, channel number, debounce figure or quality code is written into Python, and a signal the plant model does not know is reported as unconfigured rather than invented. Fault injection covers a sensor fault (no value sent at all), an out-of-range value (sent as measured, not clamped) and a link drop, after which the buffered records are replayed carrying the timestamps of the scans that produced them; `--replay` does the same for a capture taken earlier. It carries the acceptance criterion P1-03 deferred to it: the CDDL schema validates a record the simulator produces, by interpreting the schema file itself rather than a copy of its rules. That check covers the subset of CDDL the schema uses and refuses to compile anything outside it; it is not a certified CDDL implementation, because `pycddl` could not be installed on the development machine.

- The first plant signal read: the high-high level trip and the low-low heater cut-off, read as status-only inputs (story S-022, P1-05, issue #45). `firmware/src/safety/` gains a debouncing reader that takes the contact sense, the 200 ms debounce and the 50 ms scan interval from `interfaces/signals-v1.yaml` at build time, so no id, channel number or debounce figure is written into C and adding a switch to the signal list needs no C change. Both channels are normally closed, so a de-energised switch or a broken wire reads as asserted and the debouncer does not smooth that away. A state is reported as live only while fresh samples keep confirming it: a channel that chatters, or that stops being sampled, keeps its last confirmed state but is no longer live. The module is input-only by construction and has no output, relay, coil or acknowledgement path. The ztest suite on `native_sim` covers both states, the transition, a channel stuck asserted, a channel that never settles, a stopped scan loop and a millisecond-counter wrap.

### Changed

- Review rules now require one approval from a collaborator other than the author, replacing the "all three developers" rule for `interfaces/`. CODEOWNERS, the `interfaces-review` check and the pull request template were updated, and the `INTERFACE_REVIEWERS` variable set to `GamitPrince,prinz-assists` (#19). Verified end to end in #23: `interfaces-review` reports success on one non-author approval.
- `AGENTS.md` aligned with the rule above; it had asserted the old rule in three places while stating the new one in section 3 (#22).
- The electrical engineer (`@gamitriyan-del`) added as a code owner of `interfaces/`, `.github/` and `scripts/`, so that approvals on those paths do not depend on a single collaborator. Safety paths are unchanged and still require the EE.

- Simulator pins raised to clear four Dependabot alerts (S-026): `cbor2` 5.6.5 to 5.9.0, which closes two high and one moderate decoder advisory, and `pytest` 8.3.4 to 9.0.3 with `pytest-cov` 7.1.0, which pytest 9 requires. Real exposure in the simulator was low — its one `cbor2.loads` call decodes payloads it produced itself — but the cloud backend of P1-17 will decode real device CBOR off the broker, which is untrusted input, so it starts from a patched decoder. `pyproject.toml` needed no change: `cbor2>=5.6,<6` already admits 5.9.0.

### Notes

- ADR-0001 (public repository) is still Proposed. ADR-0002 (hardware) is not yet written and waits for the EE.
- The merged ADRs still carry a status line saying they are not yet pushed; correcting those lines is tracked separately.
