# S-055: Remove `gateway/` and every reference to it

- Story ID: S-055 (issue #113).
- Epic: repo chores. Points: 1. Priority: Should. Component: repository and CI. Review flag: one collaborator other than the author (`.github/` and `scripts/` are CODEOWNERS paths).

## Goal
The obsolete `gateway/` folder is gone, and nothing in the repository (CI, `pr-policy`, templates, docs) still offers or expects a gateway component.

## Phase check
Phase 1 repository housekeeping. No code, no interface, no safety path.

## Decisions already made
- **ADR-0004 decision 1:** there is no separate gateway; the FRDM collects and communicates itself.
- **Tech lead, 26 Nov 2026 (S-053 item 4):** remove `gateway/` and clean every reference. The `.github/` changes this needs (CI, CODEOWNERS, templates) are authorised for this cleanup only; rulesets are not changed.

## Files to change
- Delete `gateway/.gitkeep` (the folder's only file).
- `.github/workflows/ci.yml`: drop the `gateway` output, its entry in the change loop, the `gateway` job and its place in `ci-gate`'s `needs`. `ci-gate` stays the only required check, so the rulesets need no change.
- `.github/workflows/pr-policy.yml`: drop `gateway` from the title scopes and the error message.
- `.github/CODEOWNERS`: the comment's example folders. No owner line changes.
- `.github/ISSUE_TEMPLATE/bug-report.yml`, `story-card.yml`: drop the `gateway` component option.
- `scripts/ci/run-component.sh` (comment), `scripts/setup-github.sh` (stops creating a `gateway` label).
- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, `docs/setup-guide.md`, `docs/github-setup.md`: the folder row, scope lists and "gateway developer" wording.
- `CHANGELOG.md`.

## Out of scope
ADRs and story specs keep "gateway" where they explain history (ADR-0004 decision 1, P1-11). The `gateway` label already on GitHub is left alone: deleting it removes it from any old issue, so the tech lead decides. `docs/github-setup.md`'s other stale content (former members, the three-reviewer rule) is its own story.

## Acceptance criteria
- `git grep -i gateway` outside `docs/adr/`, `docs/stories/` and `CHANGELOG.md` finds only AGENTS.md's history notes.
- On this PR, `ci-gate` and `pr-policy` pass, and no `gateway` job appears in the checks.

## PR checklist notes
Title `chore(docs): remove gateway/ and every reference to it (S-055)`, branch `feature/S-055-remove-gateway`, `Closes #113`. No `safety` label.
