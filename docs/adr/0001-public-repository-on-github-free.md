# ADR-0001: Host tank-controller as a public repository on GitHub Free

- Status: **Proposed.** Revised by the tech lead on 26 Nov 2026 (S-054). It becomes Accepted when a collaborator other than the author approves the pull request that merges it; it is not Accepted before then.
- Date: 2026-10-27, revised 2026-11-26
- Deciders: GamitPrince (tech lead), with one approval from a collaborator other than the author

## Context

The GitHub Workflow Guide (section 12) found that on GitHub Free, private repositories cannot enforce branch protection or rulesets, and it rejected a public repository because it would expose the safety design and product. It offered three options: upgrade to Pro or Team, use a Student Developer Pack account, or follow the rules by agreement.

The team (GamitPrince, prinz-assists and the electrical engineer gamitriyan-del) is on GitHub Free. Enforced rules (mandatory pull requests, independent review, green CI, safety and interfaces approvals) are required by SOP-SDLC-001.

## Options considered

1. Public repository on GitHub Free: rulesets enforced at no cost and unlimited Actions minutes; everything committed is visible to everyone.
2. Private repository on GitHub Team: private, rulesets enforced; a monthly cost per user.
3. Private repository on GitHub Free with rules followed by agreement: private and free; nothing enforces the rules.

## Decision

Use a public repository (option 1), so rulesets are enforced at no cost. Actions minutes are free and unlimited for public repositories.

What may be public and what stays private (tech lead, 26 Nov 2026):

- **Public:** approved software source and approved documentation (ADRs, specs, interfaces, the simulator, CI).
- **Private, never committed here:** proprietary hardware design files (schematics, layouts, the EE's design and review records), safety evidence (hardware test records, EE approvals, the P1-10 no-write-path record), confidential customer information (customer names beyond those already published, site details, real data), and every secret.

Authority: GamitPrince is the tech lead for architecture and ADRs, story assignment, scope and workflow authorisation. The tech lead is **not** exempt from the rulesets: there is no bypass list (ADR-0009 amendment 1).

## Consequences

- Because the history is public, a committed secret must be rotated, not just deleted. Secret scanning and push protection stay on (ADR-0005).
- `hardware/` holds no schematics and `docs/safety/` holds no evidence. The private location is not named in this public repository.
- Outside people can fork and open issues and pull requests. They cannot approve or merge; workflows from outside contributors need approval.
- If the team later upgrades to Team, the repository can be made private and the same rulesets keep working. This ADR is then superseded. Anything already committed stays exposed.
- The Workflow Guide, section 12, must be updated to record this decision (the project manager's document).
