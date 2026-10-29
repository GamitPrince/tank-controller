# ADR-0001: Host tank-controller as a public repository on GitHub Free

- Status: **Proposed** (needs the team and the EE to accept; see Consequences)
- Date: 2026-10-27
- Deciders: [Confirm]

## Context

The GitHub Workflow Guide (section 12) found that on GitHub Free, private repositories cannot enforce branch protection or rulesets, and it rejected a public repository because it would expose the safety design and product. It offered three options: upgrade to Pro or Team, use a Student Developer Pack account, or follow the rules by agreement.

All three developers are on GitHub Free. Enforced rules (mandatory pull requests, independent review, green CI, safety and interfaces approvals) are required by SOP-SDLC-001.

## Decision

Use a public repository, so rulesets are enforced at no cost. Actions minutes are free and unlimited for public repositories.

## Consequences

- Source code, documents and commit history are visible to everyone. Nothing that must stay private may ever be committed: secrets, customer data, client-specific site details.
- [Confirm] Decide what to do with `hardware/` schematics and `docs/safety/`, which the Guide said the team did not want to expose. Options: publish them, publish PDF exports only, or keep them in a private location and link out.
- Because the history is public, a committed secret must be rotated, not just deleted.
- Outside people can fork and open issues and pull requests. They cannot approve or merge; workflows from outside contributors need approval.
- If the team later upgrades to Pro or Team, the repository can be made private and the same rulesets keep working. This ADR is then superseded.
- The Workflow Guide, section 12, must be updated to record this decision.
