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

### Changed

- Review rules now require one approval from a collaborator other than the author, replacing the "all three developers" rule for `interfaces/`. CODEOWNERS, the `interfaces-review` check and the pull request template were updated, and the `INTERFACE_REVIEWERS` variable set to `GamitPrince,prinz-assists` (#19). Verified end to end in #23: `interfaces-review` reports success on one non-author approval.
- `AGENTS.md` aligned with the rule above; it had asserted the old rule in three places while stating the new one in section 3 (#22).
- The electrical engineer (`@gamitriyan-del`) added as a code owner of `interfaces/`, `.github/` and `scripts/`, so that approvals on those paths do not depend on a single collaborator. Safety paths are unchanged and still require the EE.

### Notes

- ADR-0001 (public repository) is still Proposed. ADR-0002 (hardware) is not yet written and waits for the EE.
- The merged ADRs still carry a status line saying they are not yet pushed; correcting those lines is tracked separately.
