# S-047: Set up `esp32/` and the ESP32 end of the UART link (P1-12, fifth slice)

- Story ID: S-047 (issue #97).
- Epic: E3. Points: 3. Priority: Must. Component: ESP32 firmware (new), CI. Review flag: one non-author collaborator (`.github/` changes).

## Goal
The ESP32 firmware gets its home, `esp32/` at the top of the repo (decided by the tech lead, 25 Nov 2026), with its own `ci.sh` and CI job, and its first piece of real logic: the ESP32 end of the FRDM-to-ESP32 UART link. Bytes from the UART go in; each new RECORD's payload comes out once for the upper layer (later MQTT); a DELIVERED goes back to the FRDM only when the upper layer reports the cloud has the record.

## Phase check
Phase 1, transmit only. The ESP32 passes records from the FRDM to the cloud and sends back DELIVERED, which carries only a sequence number. **Nothing here sends a command to the FRDM or the plant**, and no message type is added. Nothing touches the safety chain.

## Decisions already made
- **Tech lead, 25 Nov 2026:** the ESP32 firmware lives in a top-level `esp32/` folder (closes the open question in `AGENTS.md` section 6).
- **ADR-0006 decisions 1 to 3:** ESP-IDF, C; logic tested with **Unity as plain C programs on a laptop and in CI**, coverage by gcovr written as Cobertura `coverage.xml` by `esp32/ci.sh`. Thin wrappers over Wi-Fi, modem, TLS and MQTT are excluded from the 80% gate and covered by recorded bench tests.
- **ADR-0004 decisions 3 to 5:** the FRDM keeps the data and the buffer; the ESP32 is the comms helper; one shared C link library for both boards.
- **S-043:** `link_receiver` is already the ESP32-side duplicate detection, built and tested on `native_sim`. DELIVERED means the cloud has the record (MQTT QoS 1), not just the UART.

## Implementation
1. **`esp32/link_endpoint.h/.c`** (standard C, no ESP-IDF calls), wrapping S-042's decoder and S-043's `link_receiver`:
   - `tank_link_endpoint_push(ep, byte)` feeds one UART byte. On a complete new RECORD it calls an injected `record_fn(ctx, seq, payload, len)` once. On a repeat of the record already confirmed it re-sends DELIVERED through an injected `write_fn`, so a lost DELIVERED does not stall the FRDM. Other frame types and bad frames are counted and dropped.
   - `tank_link_endpoint_confirm(ep, seq)` is called by the upper layer once the cloud acknowledges; it writes the DELIVERED frame.
   - Counters: frames accepted, frames rejected (by reason), records passed up, duplicates, confirms written.
2. **The shared link library stays where it is.** `esp32/` compiles `link_frame.c` and `link_receiver.c` from `firmware/src/communications/` by relative path. Moving the library to a shared folder (as `link_frame.h` already anticipates) is a later story, so this one does not touch the FRDM build.
3. **`esp32/ci.sh`**, following the contract in `scripts/ci/run-component.sh`: build the host tests with CMake and the system C compiler (`-Werror`, C11), run them, check formatting with the repository's `.clang-format`, and write `esp32/coverage.xml` with gcovr, filtered to `esp32/` sources so the FRDM's library is not counted twice. Unity is fetched at a pinned release tag into an ignored folder, like the Zephyr tree; it is never committed. Unity v2.6.1.
4. **ESP-IDF itself is not installed in CI yet.** The host build covers the logic, which is what the gate measures. Pinning the ESP-IDF version and building the real ESP32 image in CI is the story that adds the first ESP-IDF code (`app_main`, UART driver).
5. **CI wiring (`.github/workflows/ci.yml`, explicitly in scope):** add `esp32` to change detection, an `esp32` job running `bash scripts/ci/run-component.sh esp32`, and the job to `ci-gate`'s `needs`. The job also runs when `firmware/src/communications/link_*` changes, because the ESP32 compiles those files.
6. **`AGENTS.md` section 6:** record that the ESP32 firmware lives in `esp32/`; remove it from the "not yet decided" list.
7. **PR titles:** `pr-policy` has no `esp32` scope. ESP32 PRs use the `firmware` scope. Adding an `esp32` scope would mean editing `pr-policy.yml`, which this story does not do.

## Interfaces touched
None in `interfaces/`. The link frame format is unchanged.

## Acceptance criteria
- A RECORD fed in byte by byte, including one split across many pushes, reaches `record_fn` once, with its seq and exact payload.
- `tank_link_endpoint_confirm()` writes a DELIVERED that the FRDM's `link_sender` accepts for that seq.
- A resent RECORD that was already confirmed gets its DELIVERED again and does not reach `record_fn` a second time; a resent RECORD not yet confirmed is dropped silently.
- Bad CRC, bad COBS, an oversize frame and an unknown type are counted and dropped, and the endpoint resynchronises at the next delimiter.
- An end-to-end host test joins the FRDM's `link_sender` to this endpoint and shows a record confirmed once despite a lost RECORD and a lost DELIVERED.
- `esp32/ci.sh` passes locally and in CI with at least 80% line coverage; the `esp32` CI job is green and `ci-gate` requires it.

## Test plan
Unity host tests run by `esp32/ci.sh`, on Ubuntu in CI and in WSL2 locally. No bench test: no ESP-IDF code and no UART driver yet.

## Dependency
S-042, S-043 (merged).

## Out of scope
ESP-IDF `app_main`, the UART driver, Wi-Fi, the A7672S modem, TLS, MQTT, the broker, failover (ADR-0004 decision 8), secure boot and flash encryption, moving the shared library, adding an `esp32` scope to `pr-policy`, and the fate of `gateway/`.

## Decisions (tech lead, 25 Nov 2026)
All four recommendations were accepted:
- Unity v2.6.1, fetched at build time into an ignored folder and never committed.
- ESP-IDF is not installed in CI yet; its version pin and the image build come with the first ESP-IDF code.
- The shared link library stays in `firmware/src/communications/` for now.
- ESP32 pull requests use the `firmware` title scope.

## PR checklist notes
Title `feat(firmware): set up esp32/ and the ESP32 end of the UART link (S-047)`, branch `feature/S-047-esp32-link-endpoint`, `Closes #97`. No `safety` label. Needs one non-author approval (`.github/` is code-owned). CHANGELOG entry under Unreleased.
