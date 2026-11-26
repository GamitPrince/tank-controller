# S-052: Setup guide and Feature Registry (P1-24, first part)

- Story ID: S-052 (issue #107).
- Epic: E6 Documentation and release. Points: 2 of P1-24's 3. Priority: Must. Component: docs. Review flag: none.

## Goal
The parts of P1-24 that can be written now exist: a setup guide that takes a Windows machine to a green local CI run for the simulator, the firmware and the ESP32 logic, and a Feature Registry indexing every feature merged so far. The README's folder table and tool-version line stop being stale.

## Phase check
Documentation only.

## Decisions (P1-24's open questions; the recommended answers, taken on the tech lead's standing instruction of 25 Nov 2026) [Confirm]
1. **Split P1-24.** This story is the part that can be done now. The runbook, the onboarding note and the second-person bring-up test come in a second story once the cloud exists (P1-17), because there is nothing to run yet.
2. **No back-filled Feature Completion Documents.** The registry back-fills every merged feature with its story, PR, code and tests; the merged PR and spec carry the detail. `docs/features/completed/` stays for documents from here on if the tech lead wants them.
3. **Second-person check:** prinz-assists, who did not write the guide, follows it on their own machine. The guide says it is unverified until then.

## Files to create or change
- `docs/setup-guide.md` (new): tools, clone, simulator, firmware in WSL2 (with the path-with-a-space and old Python/CMake traps found on 25 Nov 2026), ESP32 host tests, before-a-PR checks.
- `docs/features/README.md` (new): the Feature Registry.
- `README.md`: add `esp32/`, point at the guide and the registry, replace the stale tool-version line.
- `docs/stories/P1-24-documentation-set.md`: status line.

## Interfaces touched
None.

## Acceptance criteria
- Every path the registry names exists.
- The guide's commands are the ones CI runs (`scripts/ci/run-component.sh <component>`).
- `docs-links` passes.

## Test plan
`docs-links` CI check; every registry path checked with `ls`.

## Out of scope
The runbook and onboarding note (second P1-24 story). `docs/github-setup.md` still names ArkinGamit and SHINE-18 and the old "three reviewers" rule, but `scripts/setup-github.sh` itself still enforces three reviewers, so fixing the guide means changing a CODEOWNERS script; that is its own story.

## PR checklist notes
Title `docs(docs): add the setup guide and Feature Registry (S-052)`, branch `feature/S-052-setup-guide-and-feature-registry`, `Closes #107`.
