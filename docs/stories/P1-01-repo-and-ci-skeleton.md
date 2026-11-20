# P1-01: Set up repository structure, branch protection, pull request template and CI skeleton

- Story ID: `[Confirm]` — not yet issued. Next free is S-012.
- Epic: E1 Foundation. Points: 3. Priority: Must. Component: docs. Review flag: none.
- Status: **Done, with one residual item.**

## Goal
The repository enforces the playbook's rules by configuration, not by agreement.

## Phase check
Repository configuration only. No code, no safety function.

## What is already done
- Folders exist: `firmware/`, `gateway/`, `dashboard/`, `simulator/`, `hardware/`, `interfaces/`, `docs/`, plus `scripts/` and `.github/`.
- Rulesets `protect-main-develop` and `protect-version-tags` are active with no bypass actors: no direct push, PR required, one non-author approval, approval of the latest push, stale approvals dismissed, code-owner review, conversations resolved, squash only, linear history, branch up to date.
- Required checks `ci-gate`, `pr-policy`, `interfaces-review` all report. Verified green on PRs #22, #23 and #24; `interfaces-review` verified in all three states.
- `PULL_REQUEST_TEMPLATE.md` carries the 7-item playbook checklist. `pr-policy` enforces title, branch, story link, checklist, safety label and forbidden files.
- CODEOWNERS covers safety paths (EE only) and `interfaces/`, `.github/`, `scripts/`.

## What is left
**No component has a `ci.sh`.** The CI contract in `CONTRIBUTING.md` says each of `firmware/`, `gateway/`, `dashboard/`, `simulator/` needs one that builds, lints, tests and writes a Cobertura `coverage.xml`, and that a folder with code but no `ci.sh` fails CI. The folders are empty so CI passes today, but the first code in any of them will fail. Overlaps P1-00 criterion 4.

## Acceptance criteria (from the story card)
- Folders for firmware, gateway, dashboard, simulator, hardware, interfaces and docs exist. **Met**
- Direct pushes to `main` and `develop` are blocked. **Met**
- A PR with failing CI or no reviewer cannot merge. **Met and demonstrated**
- The PR template carries the playbook checklist. **Met**

## Conflicts with the ADRs
- **`gateway/` should probably not exist.** ADR-0004 decision 1 removes the separate gateway, but the folder, its CI job, its `pr-policy` scope and the README row remain. Deleting it is a decision for the tech lead, not this story.
- `firmware/src/` placeholders (`drivers/`, `control/`, `analytics/`) do not match ADR-0003's four layers (hardware, measurement, record, communications). The firmware skeleton story decides the layout; `control/` and `analytics/` must stay empty in Phase 1.

## Out of scope
Writing the `ci.sh` files, removing `gateway/`, reorganising `firmware/src/`.

## Open questions
- `[Confirm]` Close this story as done and track `ci.sh` separately, or hold it open until the `ci.sh` files exist?
- `[Confirm]` What happens to `gateway/`?
