# CHORE-03: Read the pull request's labels from the API, not from the event payload

- Story ID: `[Confirm]` — not yet issued. A **repo chore**, so it has no `P1-xx`
  ID. This spec was delivered by S-024.
- Points: **1 (proposed)**. Priority: Should — it does not block a merge, but it
  puts a red check on a correct pull request and sends the author looking for a
  fault that is not there.
- Component: repo tooling (`.github/`). Review flag: `.github/` is a CODEOWNERS
  path, so one approval from `@GamitPrince`, `@prinz-assists` or
  `@gamitriyan-del` other than the author.

## Goal

`pr-policy` must judge a pull request by the labels it has **now**, so that a
label added a second after the pull request was opened is seen, and so that
re-running a failed run can clear it.

## The defect, as observed

On PR #46 (story S-022, `firmware/src/safety/`) on 21 Nov 2026:

- The `safety` label was present on the pull request, together with `firmware`,
  `story` and `must`.
- `pr-policy` run 44899188231 failed with
  `This PR touches a safety path. Add the "safety" label; the EE must approve
  (enforced by CODEOWNERS).`
- Four other `pr-policy` runs on the same commit, from the `labeled` events,
  **passed**.
- `gh run rerun 44899188231` produced attempt 2, which **failed identically**.

## Why

`.github/workflows/pr-policy.yml` line 30:

```js
const labels = pr.labels.map(l => l.name);
```

`pr` is `context.payload.pull_request`, a snapshot of the pull request as it was
when the event fired. `gh pr create --label ...` creates the pull request first
and attaches the labels immediately afterwards, so the `opened` event carries an
empty label array. Re-running a workflow run **replays the same payload**, which
is why attempt 2 cannot pass: there is no label in the payload to find, however
many labels the pull request now has.

Note that the file reads other fields from the payload too (`pr.title`,
`pr.body`, `pr.head.ref`, `pr.base.ref`, `pr.additions`), and already calls the
API for the files list and for the linked issue. Only the label read is affected
by this race, because a label is the one attribute routinely set after creation.

## What is **not** wrong

- The rule itself is correct and must stay: a pull request touching
  `firmware/src/safety/` or `docs/safety/` needs the `safety` label.
- The checklist, title, branch and story-link rules are unaffected.
- No ruleset, CODEOWNERS entry or required check is weakened by this fix. The
  check still fails a pull request that genuinely lacks the label.

## Decision to make first

`[Confirm]` **Does the tech lead want this changed at all?** The present
behaviour is survivable: a later event passes, and attaching labels before
opening the pull request avoids it. The cost of leaving it is one misleading red
check per pull request created with labels in one command, and an author who
cannot clear it by re-running. AGENTS.md section 11 forbids editing
`.github/workflows/` without a spec that says so, which is why this spec exists
rather than a change.

## How to do it

1. Branch from `develop` as `bugfix/S-0xx-pr-policy-label-source`.
2. In `.github/workflows/pr-policy.yml`, fetch the pull request before the rule
   block and take the labels from the response rather than the payload:

   ```js
   const { data: current } = await github.rest.pulls.get(
     { owner, repo, pull_number: pr.number });
   const labels = current.labels.map(l => l.name);
   ```

   `permissions: pull-requests: read` is already granted, so no permission
   change is needed. Leave every other payload read alone: this chore fixes the
   label source only.
3. Add a comment above it saying why, so the next reader does not "simplify" it
   back to the payload.
4. Do not touch any other rule, and do not change the workflow's triggers.

## Acceptance criteria

1. A pull request opened with `gh pr create --label safety ...` on a branch that
   touches `firmware/src/safety/` has a **green** `pr-policy` on its first run.
2. A pull request that touches a safety path and genuinely has no `safety` label
   still **fails**, with the same message. Proven deliberately, not assumed.
3. Re-running a `pr-policy` run that failed for a missing label, after the label
   is added, **passes** — which is the behaviour that is impossible today.
4. No other `pr-policy` rule changes behaviour: title, branch, story link,
   checklist, forbidden files and the `main` changelog rule all still fail when
   they should. The quickest honest check is one deliberately malformed pull
   request title on a scratch branch.
5. No check, ruleset, CODEOWNERS entry or coverage gate is edited, skipped or
   weakened.

## Test plan

Bench only; no simulator or hardware involvement. The test is the workflow
running on real pull requests:

- Criterion 1 on the chore's own pull request, if it is given a label at
  creation time.
- Criteria 2 and 4 on a throwaway branch, each failure recorded in the pull
  request before the branch is deleted.
- Criterion 3 by re-running the run from criterion 2 after adding the label.

## Risks

1. **An extra API call per run.** One `pulls.get` against a 5-minute job with a
   generous rate limit. Negligible.
2. **It touches a policy file.** The fix must be reviewed as a policy change,
   not as a convenience: the reviewer's job is to confirm the rule still fails
   a pull request that deserves it, which is criterion 2.
3. **The race is invisible once fixed.** Nobody will notice it working. Record
   the before and after run links in the pull request so the next person does
   not re-derive the diagnosis.

## Out of scope

- Every other `pr-policy` rule, and the `interfaces-review` workflow.
- The two other known workflow chores: cppcheck is still advisory, and the
  Zephyr tree is not cached.
- Changing how pull requests are created (for example always labelling before
  opening). That is a workaround for this defect, not a fix, and it cannot help
  a label added later by a reviewer.

## Dependency

None.
