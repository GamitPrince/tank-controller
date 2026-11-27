# S-081: Refresh AGENTS.md to the state after S-080

- Story ID: S-081 (issue #165).
- Epic: none (repo documentation). Points: 1. Priority: Should. Component: docs. Review flag: one collaborator other than the author.

## Goal
`AGENTS.md`, the brief every coding session reads first, matches the repository after S-080 again. It was last refreshed on 26 Nov 2026 (S-053), before S-054 to S-080 merged, and still says there is no firmware application and no backend.

## Phase check
Documentation only. No code, no interface, no safety path.

## Decisions already made
- The 26 Nov 2026 order of work (S-053 to the backend skeleton) is complete. Later stories are chosen one at a time by the tech lead; this story records no new order.
- Backend pull requests use the `dashboard` title scope (S-066 [Confirm] 1).
- The RSD, the story cards, the ADR files, CODEOWNERS, rulesets and `.github/` are not edited here (AGENTS.md section 11).

## Files to change
- `AGENTS.md`: the "Last updated" line; section 3 (the process lessons below); section 6 (the backend as merged, S-057 done); section 10 (state, not done, what blocks deployment, the order).
- `docs/stories/README.md`: the date line and the rows that are stale or missing for S-054 to S-065 (P1-00, P1-12, P1-14, P1-17, P1-20, CHORE-01, the totals, the "queued" line and backlog items 3 and 4), and a row for S-081.
- `CHANGELOG.md`: one line under Notes.
- This spec.

## Interfaces touched
None.

## Acceptance criteria
- Section 10 lists S-054 to S-080 as done, names what is not done and what still blocks any deployment, and says the 26 Nov order is complete with no invented order after it.
- Section 6 describes `backend/tankapi/` and `backend/migrations/` as merged.
- Section 3 records the four lessons since 26 Nov 2026, each verified in the repository or on GitHub: a stacked PR conflicts after its base is squash-merged and is fixed by merging `develop` in (PR #164, merge commit `52d1dbd`); a `pr-policy` run on a merged PR fails with "#N is closed" and is harmless (PR #160, run 45975485385); `*.hex` is ignored, so hex fixtures are `.txt`; backend PRs use the `dashboard` scope.
- Nothing is stated that cannot be checked against `git log`, the merged specs, `gh issue list` or `gh pr list`; anything else is left out or marked `[Confirm]`.
- `docs-links` passes.

## Test plan
`python scripts/check_links.py` locally and the `docs-links` CI check; read the changed text against `git log origin/develop`, the specs S-054 to S-080 and `gh issue list --state all`.

## Out of scope
Any code. The ADR files, the RSD and story cards. The "Story ID naming" section of `docs/stories/README.md`, which still says the next free ID is S-012 (historical; a separate cleanup if wanted). Any new decision or order of work.

## Open questions [Confirm]
Both **confirmed by the tech lead, 27 Nov 2026**.
1. **Local database on the development machine.** No Docker is installed; a PostgreSQL 18 install exists (`C:\Program Files\PostgreSQL\18\bin`) but no story has used it, and whether it runs or has TimescaleDB is unchecked. Recorded as found, not as a decision.
2. **Approvals after a merge push.** A force-push dismisses an approval; whether a merge commit pushed after an approval keeps it has not been tried in this repository, so AGENTS.md says to merge `develop` in before asking for review.

## PR checklist notes
Title `docs(docs): refresh AGENTS.md to the state after S-080 (S-081)`, branch `feature/S-081-refresh-agents-md`, `Closes #165`. No `safety` label. `interfaces/` is not changed.
