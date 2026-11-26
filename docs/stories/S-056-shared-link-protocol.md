# S-056: Move the link protocol library to `shared/link-protocol/`

- Story ID: S-056 (issue #115).
- Epic: E3 (P1-12). Points: 1. Priority: Must. Component: FRDM firmware and ESP32 firmware build. Review flag: one collaborator other than the author (`.github/` is a CODEOWNERS path).

## Goal
The FRDM-to-ESP32 link library lives in one folder that belongs to neither board, before the ESP32 work grows. Both boards build the same files and both integrations stay tested. No behaviour changes.

## Phase check
Phase 1, transmit path only. Nothing is added to the protocol; no message type carries a command. No safety path.

## Decisions already made
- **ADR-0004 decision 5:** one framed protocol (COBS, sequence numbers, CRC, delivery confirmation) in a shared C library.
- **ADR-0006 decision 2:** written once in C and compiled for both boards.
- **Tech lead, 26 Nov 2026 (S-053 item 16, ADR-0003 amendment 1):** move it to `shared/link-protocol/`; both use the same implementation; preserve COBS framing, sequence numbers, CRC and delivery confirmation; test both integrations.

## Implementation
1. `git mv` `link_frame`, `link_receiver` and `link_sender` (`.c` and `.h`) from `firmware/src/communications/` to `shared/link-protocol/`, unchanged apart from one stale comment in `link_frame.h`. A `README.md` there says what each file does and who builds it.
2. **FRDM tests:** `communications_link_frame`, `communications_link_delivery`, `communications_uplink`, `hardware_esp32_uart` and `record_cbor` compile or include the library from `shared/link-protocol/`. No test code changes.
3. **ESP32 tests:** `esp32/tests/CMakeLists.txt` points `LINK_DIR` at `shared/link-protocol/`.
4. **`firmware/ci.sh`:** clang-format (with `firmware/.clang-format`) and cppcheck also cover `shared/link-protocol/`, and gcovr's root becomes the repository root with filters for `firmware/src/` and `shared/link-protocol/`, so the library stays inside the firmware job's 80% gate exactly as before.
5. **`esp32/ci.sh`:** comment only. It still counts `esp32/components/` alone, so the library is not counted twice.
6. **`.github/workflows/ci.yml`:** the `changes` step runs the `firmware` job for `shared/` changes and the `esp32` job for `shared/link-protocol/` changes (it watched `firmware/src/communications/link_*` before). Without this, a change to the library would run neither job. `[Confirm]` this workflow edit; it is the minimum the move needs and changes no required check.

## Interfaces touched
None. The frame format, record schema and APIs do not change.

## Acceptance criteria
- `firmware/src/communications/` holds no `link_*` file; `shared/link-protocol/` holds all six.
- The firmware CI passes with every suite, and the library's lines appear in `firmware/coverage.xml`; overall coverage stays at or above 80%.
- The ESP32 CI passes (`test_link_endpoint`, `test_link_e2e`).
- On this PR, both the `firmware` and the `esp32` jobs run.

## Test plan
`native_sim` and the ESP32 host build, run locally (WSL) and in CI. No bench test: nothing a board runs has changed.

## Out of scope
Making `shared/` its own CI component, moving `.clang-format` to the repository root, an ESP-IDF component wrapper for the library (comes with the ESP-IDF build), and any protocol change.

## PR checklist notes
Title `refactor(firmware): move the link protocol library to shared/link-protocol/ (S-056)`, branch `feature/S-056-shared-link-protocol`, `Closes #115`. No `safety` label.
