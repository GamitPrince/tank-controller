# S-099: Refresh AGENTS.md to S-098

- Story ID: S-099 (issue #201).
- Epic: none (repo documentation). Points: 1. Priority: Should. Component: docs. Review flag: one collaborator other than the author.

## Goal
`AGENTS.md`, the brief every coding session reads first, matches the repository after S-098 again. It was last refreshed on 27 Nov 2026 (S-081), before S-082 to S-098 merged, and still says the simulator emits single records, that PostgreSQL is unchecked and that S-079's triggers are untested on a server.

## Phase check
Documentation only. No code, no interface, no safety path.

## Decisions already made
- Later stories are chosen one at a time by the tech lead; this story records no order of work (S-081).
- Backend pull requests use the `dashboard` title scope (S-066 [Confirm] 1).
- The RSD, the story cards, the ADR files, CODEOWNERS, rulesets and `.github/` are not edited here (AGENTS.md section 11).
- S-098's local setup: PostgreSQL 18.6 with TimescaleDB 2.30.0 installed and preloaded but unused, the login `tankai_dev` and the NOLOGIN role `tankapi_backend`, made by the tech lead by hand (S-098 spec, "Local setup").

## Files to change
- `AGENTS.md`: the "Last updated" line; section 3 (the approval lesson below); section 6 (the backend as merged after S-098); section 10 (state, not done, what blocks deployment, the open candidates).
- `docs/stories/README.md`: the date line, the rows still marked "in review" for merged stories (S-083 to S-086, S-094, S-097, S-098), the P1-02, P1-04, P1-18 and P1-19 notes, the totals sentence, and a row for S-099.
- `CHANGELOG.md`: one line under Notes.
- This spec.

## Interfaces touched
None.

## Acceptance criteria
- Section 10 lists S-082 to S-098 as done, no longer says the simulator emits single records, and names what is not done and what still blocks any deployment: the daily S3 Object Lock audit copy, the Cognito user pool, ADR-0007's three gates and a Postgres service in GitHub CI.
- Section 6 names the backend modules, migrations `0005` to `0008`, `backend/sql/backend-role-grants.sql` and the opt-in Postgres tests (`TANKAPI_TEST_DATABASE_URL`, login `tankai_dev` through `pgpass.conf`, role `tankapi_backend`). No password is written anywhere.
- Section 3 records that a merge of `develop` pushed after an approval dismissed it on PR #176 ("The merge-base changed after approval."), replacing the earlier `[Confirm]`.
- Nothing is stated that cannot be checked against `git log`, the merged specs, `gh issue list` or `gh pr view`; anything else is left out or marked `[Confirm]`.
- `docs-links` passes.

## Test plan
`python scripts/check_links.py` locally and the `docs-links` CI check; read the changed text against `git log origin/develop`, the specs S-082 to S-098, `ls backend/tankapi backend/migrations/versions` and the PR #176 timeline.

## Out of scope
Any code. The ADR files, the RSD and story cards. The "Story ID naming" section of `docs/stories/README.md`. Any new decision or order of work.

## Open questions [Confirm]
1. **Why the approvals on stacked PRs were dismissed.** On PR #176 the dismissal came with the develop merge push; on PR #180 a dismissal at 13:24 has no message. Recorded as seen, not as a rule of GitHub.

## PR checklist notes
Title `docs(docs): refresh AGENTS.md to S-098 (S-099)`, branch `feature/S-099-refresh-agents-md`, `Closes #201`. No `safety` label. `interfaces/` is not changed.
