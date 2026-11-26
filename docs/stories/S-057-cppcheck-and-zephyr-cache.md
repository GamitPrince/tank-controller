# S-057: Make cppcheck blocking and cache the Zephyr tree in CI

- Story ID: S-057 (issue #117).
- Epic: repo chores (closes the two CI items CHORE-01 left open). Points: 2. Priority: Should. Component: CI and the firmware CI script. Review flag: one collaborator other than the author (`.github/` is a CODEOWNERS path).

## Goal
cppcheck findings of the configured severities fail the firmware job, and the firmware job stops re-fetching an unchanged Zephyr tree when that saves time, without ever reusing a tree from another Zephyr version.

## Phase check
Phase 1 CI housekeeping. No firmware behaviour changes and no safety path.

## Decisions already made
- **ADR-0003 decision 7:** cppcheck for static analysis, run from `firmware/ci.sh`.
- **Tech lead, 26 Nov 2026 (S-053 item 15, ADR-0003 amendments 2 and 3):** configured cppcheck errors block CI, with reviewed severities and suppressions; Zephyr dependencies are cached, keyed on the Zephyr version, the manifest and the dependency lock; one dedicated story under normal review and CI rules.
- **AGENTS.md section 3:** GitHub-owned actions only. `actions/cache` is GitHub-owned.

## Implementation
1. **cppcheck installed in CI:** the firmware job installs it with `apt-get` before `firmware/ci.sh` runs. In CI a missing cppcheck now fails the job; a developer machine without it still only gets a warning.
2. **Severities** (`firmware/ci.sh`): errors, `warning` and `portability` findings block (`--error-exitcode=1`). `style` and `performance` findings run in a second, non-blocking pass so the reviewer sees them. Both passes cover `firmware/src/` and `shared/link-protocol/`, with `--std=c11`.
3. **Suppressions:** inline only (`--inline-suppr`), each next to the code it hides with a one-line reason, so a suppression is reviewed with that code. No global suppression list.
4. **Zephyr cache** (`.github/workflows/ci.yml`): `actions/cache` over the west workspace (`.west`, `zephyr`, `modules`, `bootloader`, `tools`). The key hashes `firmware/west.yml` (which pins Zephyr v4.5.0, and through `import: true` every module revision) and `firmware/requirements-dev.txt` (the pinned west). No `restore-keys`, so a changed pin is always a miss. `west update` still runs after a hit and corrects any drift.

## Measured before this story
In PR #116's firmware job the fetch took 1 min 48 s of 4 min 35 s, and the fetched tree is about 6 GB (5.6 GB of it modules, because `import: true` pulls every Zephyr module). A cache entry that large uses most of the repository's 10 GB cache quota, and restoring it may not be much faster than fetching. This PR measures it: the first run saves the entry, a re-run restores it.

## Findings fixed in this PR
- `firmware/src/record/scan_codec.c` `put_svar`: zigzag encoding right-shifted a negative `int64_t` (`shiftTooManyBitsSigned`), which C leaves implementation-defined. It now works on the unsigned bits; the encoded bytes are the same. A new test, `test_extreme_values_and_deltas_round_trip`, round-trips readings jumping between `INT32_MIN` and `INT32_MAX` in both directions.
- `actions/cache` is `@v6` (the latest release); `@v4` runs on the deprecated Node 20.

## Open questions [Confirm]
1. **Keep the cache?** Only if the measured restore is clearly faster than the 1 min 48 s fetch.
2. **A develop warm-up.** CI runs only on pull requests, and a pull request's cache entry is visible only to that pull request. Every new PR would therefore start cold unless a run on `develop` saves the entry. That needs a small extra workflow (on merge to `develop` and on a schedule), which is not in this PR.
3. **Fetch less instead.** A `name-allowlist` in `west.yml` (Zephyr plus the modules the FRDM-MCXN947 build needs) would shrink both the fetch and any cache. That is a manifest change and its own story.

## Interfaces touched
None.

## Acceptance criteria
- The firmware job's log shows cppcheck running, and the job fails on a blocking finding.
- Any finding fixed or suppressed in this PR is listed in the PR with its reason.
- The cache key changes when `firmware/west.yml` or `firmware/requirements-dev.txt` changes, and no restore key exists.
- All other jobs and the 80% gate are unchanged.

## Test plan
GitHub CI on this pull request: the first run shows the cppcheck results and saves the cache, and a re-run shows the restore time. Nothing runs locally outside the repository.

## Out of scope
MISRA checking (Phase 2, ADR-0003 decision 7). cppcheck on `esp32/` (its own story if wanted). The warm-up workflow and the west allowlist (questions 2 and 3).

## PR checklist notes
Title `chore(firmware): make cppcheck blocking and cache the Zephyr tree in CI (S-057)`, branch `feature/S-057-cppcheck-and-zephyr-cache`, `Closes #117`. No `safety` label.
