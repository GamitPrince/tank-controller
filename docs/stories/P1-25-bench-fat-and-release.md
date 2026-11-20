# P1-25: Run the bench factory acceptance test with the simulator and tag `sys-v0.1.0`

- Story ID: `[Confirm]` — not yet issued.
- Epic: E6. Points: 5. Priority: Must. Component: simulator, docs. Review flag: none.
- This is the **Phase 1 exit gate**.

## Goal
Demonstrate every Must story working together on the bench, then cut the first system release.

## Phase check
Phase 1 complete. Nothing new is built here; it is proof plus a release.

## Decisions already made
- **Release flow** (playbook): all sprint stories done, branch `release/vX.Y.Z` from `develop`, final bench test, fix last bugs, update `CHANGELOG.md`, PR into `main`, tag, merge back to `develop`, GitHub Release with notes and firmware binaries, record which `sys-` tag is at the pilot.
- **Repo rules:** only `release/*` and `hotfix/*` may target `main`; PRs into `main` **must** update `CHANGELOG.md`; version tags `v*.*.*` are protected; squash merge and linear history.
- **ADR-0003 and ADR-0006:** bench tests on real hardware are recorded, and they cover exactly what the simulated-chip and thin-wrapper coverage exclusions do not. This story is where those recorded bench tests land.
- **ADR-0007:** Phase 1 firmware updates are **by cable only**.

## Tag naming conflict to resolve
The story card says tag **`sys-v0.1.0`**. The protected-tag ruleset protects **`v*.*.*`**. Whether `sys-v0.1.0` matches that pattern needs checking before release day — if it does not, the component tags (`fw-`, `gw-`, `dash-`, `sys-`) are unprotected, which defeats the purpose. `[Confirm]` and fix the ruleset pattern if needed; that is a settings change, not a code change.

## Acceptance criteria (from the story card)
- Acceptance criteria of **all Must stories** are shown on the bench.
- **No open Critical or High bugs.** Any defect in a safety function is automatically Critical and stops the release.
- `CHANGELOG.md` updated.
- Release pull request raised into `main`.
- The `sys-` tag is recorded.
- Plus: the EE's recorded approvals and test results for P1-05, P1-09 and P1-10 are in place before release.

## Test plan
The FAT itself: a scripted run through every Must story's criteria against real hardware plus the simulator where sensors are missing, with results written down. Include the deliberately awkward cases: sensor failure, 24-hour outage recovery, clock never synced, certificate revoked, stale flag.

## Dependency
Everything. Realistically also the hardware availability question (card question 6) and the three ADR-0007 cloud gates.

## Out of scope
Phase 2 features. Site installation and commissioning.

## Open questions
- `[Confirm]` Does `sys-v0.1.0` fall under the protected tag pattern?
- `[Confirm]` Which Should stories, if any, must be in `v0.1.0`? P1-08 and P1-23 are Shoulds.
- `[Confirm]` Who signs off the FAT? `AGENTS.md` records that the QA sign-off owner is **not assigned**.
- `[Confirm]` Is the pilot-site hardware the first revision, and which sensors are available for the bench?
