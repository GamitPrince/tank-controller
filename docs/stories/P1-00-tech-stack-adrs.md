# P1-00: Choose the tech stack and record each decision as an ADR

- Story ID: **S-002** (issue #3). Already created and merged in part.
- Epic: E1 Foundation. Points: 5. Priority: Must.
- Component: docs. Review flag: one non-author collaborator (was ALL3); EE on the hardware ADR.
- Status: **Partly done.**

## Goal
One ADR per layer, in `docs/adr/`, giving the options considered, the decision and the reasons.

## Phase check
Documentation only. No code, no safety function.

## What is already done
ADR-0003 (firmware) to ADR-0009 (CI and deployment) are written, reviewed by `prinz-assists` and merged as PRs #11 to #17 under stories S-003 to S-009.

## What is left
1. **ADR-0002 (hardware)** is unwritten and waits for the EE. Do not write it; it is the EE's decision to record. Needs the EE's approval per the review flag.
2. **ADR-0001 (public repository)** is still status Proposed and has out-of-date points (hardware files, tech lead authority).
3. **The seven merged ADRs still say "Not yet pushed to GitHub"** and describe themselves as not yet Accepted. They are merged, so the status lines are wrong. ADR-0009 needs an explicit note that its rule 7 (tech lead bypass list) is **not** applied in GitHub.
4. **"A minimal skeleton in each layer builds in CI"** is not met. No component has a `ci.sh`, so no layer builds. This overlaps P1-01 and the 80% coverage gate; decide which story owns it `[Confirm]`.

## Acceptance criteria (from the story card)
- One ADR per layer in `docs/adr/` with options, decision and reasons.
- All three developers review each ADR and the EE reviews the hardware ADR. **Superseded by S-010:** one approval from a collaborator other than the author; safety and hardware keep the EE.
- Every chosen tool is free or has a recorded cost approval.
- A minimal skeleton in each layer builds in CI.

## Conflicts with the ADRs
- The review flag ALL3 no longer exists. S-010 replaced it.
- "Every chosen tool is free or has a recorded cost approval": ADR-0007 names paid managed services (AWS, Tiger Cloud) behind three gates. The cost approval is the gate record, not a free-tool claim. `[Confirm]` that this satisfies the criterion.

## Out of scope
Writing ADR-0002. Re-deciding anything in ADR-0003 to ADR-0009.

## Open questions
- `[Confirm]` Which story owns "a minimal skeleton builds in CI": this one, P1-01, or a new chore story?
- `[Confirm]` Does the ADR-0007 gate record count as the recorded cost approval?
