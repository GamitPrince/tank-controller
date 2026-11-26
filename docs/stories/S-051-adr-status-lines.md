# S-051: Mark the seven merged ADRs as Accepted

- Story ID: S-051 (issue #105).
- Epic: none (repo documentation). Points: 1. Priority: Should. Component: docs. Review flag: none.

## Goal
ADR-0003 to ADR-0009 were approved by a collaborator other than the author and merged on 20 Nov 2026 (PRs #11 to #17), but each still says "Not yet pushed to GitHub" and "becomes Accepted when one collaborator other than the author approves the PR". Their status lines are corrected so a reader, auditor or customer sees decided records.

## Phase check
Documentation only. No decision inside any ADR changes.

## Decisions already made
- AGENTS.md section 4: treat the merged ADRs as decided; correcting the status lines is its own story.
- PRs #11 to #17 were each approved by prinz-assists and merged on 20 Nov 2026 (checked with `gh pr view`).

## Files to change
- `docs/adr/ADR-0003` to `ADR-0009`: line 3 only. Each becomes "Accepted", keeps the tech lead's confirmation date and scope, and names the approver and the PR. ADR-0007 keeps its three cloud gates. ADR-0009 says rule 7 is decided but not applied in GitHub.
- `AGENTS.md` section 4: the "Known wart" paragraph.
- After S-050 (PR #104) merges: the same wart where it is repeated in `AGENTS.md` section 10 and in `docs/stories/README.md` (the P1-00 row and backlog item 4).

## Interfaces touched
None.

## Acceptance criteria
- No merged ADR says "Not yet pushed" or "becomes Accepted".
- Nothing below line 3 of any ADR changes.
- ADR-0001 is untouched: it is still Proposed, and accepting it is the tech lead's decision.

## Test plan
`grep -rn "Not yet pushed\|becomes Accepted" docs/adr AGENTS.md docs/stories/README.md` finds nothing; `docs-links` passes.

## Out of scope
ADR-0001, ADR-0002, applying rule 7 in GitHub, and the other `[Confirm]` notes inside the ADRs.

## Open questions
None.

## PR checklist notes
Title `docs(docs): mark the seven merged ADRs as Accepted (S-051)`, branch `feature/S-051-adr-status-lines`, `Closes #105`.
