# ADR-0009: CI and deployment: cloud blueprints, environments, deployment, AWS access, monitoring and security checks

- Status: Confirmed by the tech lead on 19 Nov 2026, including rule 7 (full tech lead authority) and its recorded downsides; becomes Accepted when one collaborator other than the author approves the PR. Not yet pushed to GitHub.
- Date: 19 Nov 2026
- Story: P1-00 (issue S-002); shapes P1-01 (repository and CI skeleton) and the cloud and dashboard stories (to be created)
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0003 (firmware), ADR-0005 (security), ADR-0006 (ESP32 firmware), ADR-0007 (cloud), ADR-0008 (backend and dashboard)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

The repository already has a shared check, `ci-gate`, that runs each component's `ci.sh` and requires 80% line coverage as a Cobertura `coverage.xml` (GitHub Workflow Guide). Firmware has its own toolchains (ADR-0003 Zephyr, ADR-0006 ESP-IDF). ADR-0007 puts the cloud on AWS (IoT Core, a managed queue, containers on a managed service, S3, Cognito) with Tiger Cloud as the database, and ADR-0008 adds a Python backend and a React dashboard, each with its own `ci.sh`. Nothing yet says how the cloud is created, how many copies of it exist, how code reaches it, how the pipeline logs in to AWS, how we notice problems, or which automatic security checks run. The repository is public (ADR-0001) and may become private later. Most of the code is written by the tech lead with AI, and customers such as Siemens or Astec will ask how releases are controlled.

## Decisions

1. **Cloud blueprints:** the AWS setup (IoT Core, queue, containers, storage, login, alarms) and the Tiger Cloud setup are written as code in Terraform or OpenTofu, kept in the repository (folder to be set in P1-01), and changed only through pull requests. One tool covers both vendors. The same files create the test and the live copy. AWS CDK (Python) was not chosen because it covers AWS only. Setting things up by hand in the console was not chosen: nothing is written down, nobody can review it, and a rebuild after a mistake is slow.
2. **Environments:** two cloud copies, test and live. The test copy is fed by the simulator and bench units and can be small or switched off when idle. Every release is proven on test before live. A third developer copy was not chosen (too much setup and cost for the team size now). A single live copy was not chosen (new code would be tried first on real customer data).
3. **Deployment:** GitHub Actions deploys. A merge to `develop` deploys to the test copy automatically. A release tag created from `main` deploys to live only after a second person approves in a GitHub environment (same pattern as the firmware signing key, ADR-0005 decision 4). Rollback is redeploying the previous tag. Fully automatic deployment to live was not chosen, and neither was deployment by hand from a laptop. The approval step works free while the repository is public; if it goes private, the plan limits must be checked first (see consequences).
4. **AWS access for the pipeline:** the pipeline gets short-lived passes through OIDC (GitHub proves its identity to AWS), limited to this repository and to a separate role for test and for live. No permanent AWS key is stored in GitHub. A permanent key in GitHub secrets was not chosen, because a leak would give full access until someone noticed.
5. **Monitoring:** AWS's built-in tools: logs, metrics and alarms, sent by email or SMS through AWS's alert service, all defined in the blueprints. Alerts include: no data from a device for a set time, backend errors, queue backlog, database storage, failed deployments, and the monthly cost budget from ADR-0007. The alert limits are set in P1-01 and tuned in testing. A separate monitoring vendor was not chosen for Phase 1 (a new vendor, bill and security review); it can be added if a customer asks. Looking by hand was not chosen.
6. **Pipeline checks:** besides the tests and the 80% gate (ADR-0008 decision 6), every pull request runs the free GitHub set: dependency alerts and update pull requests (Dependabot), secret scanning with push protection (ADR-0005), code scanning (CodeQL), and a vulnerability scan of the container images at build. High and Critical findings block the merge. The shared `ci-gate` runs each component's `ci.sh` for the components a pull request changes (backend, dashboard, firmware, ESP32, simulator). A paid scanning vendor was not chosen; it can be added if a customer asks.

Rule 7 (first proposed as a lighter rule; changed by the tech lead on 19 Nov 2026 to full tech lead authority, confirmed with the ADR):

7. **Tech lead authority (changed by the tech lead on 19 Nov 2026 from the proposed lighter rule):** the repository stays public for now, and the tech lead (GamitPrince) has final authority over the repository. He can merge his own pull requests, approve his own live releases and firmware signing, and change `.github/`, the safety folders and the rules themselves, with no second person needed. In GitHub this is done by putting him on the bypass list of the rulesets, so the rules stay in place for everyone else. The automatic checks (`ci-gate`, `pr-policy`, `interfaces-review`) stay on for other people's pull requests and keep running for his. The tech lead changes the GitHub settings by hand; this ADR does not change them. Going private is decided later. This rule overrides, for the tech lead only: the second-person approval of ADR-0005 decision 4 (safeguard b), CODEOWNERS approval by the EE on the safety folders, the "all three developers" review of `interfaces/`, and the approval rule of the GitHub Workflow Guide. Other people still follow the rules as written.

## Consequences

- Terraform or OpenTofu is a new tool to learn, and its state (the record of what exists in AWS) must be kept safely and backed up. Where the state lives and who may change it is decided in P1-01. [Confirm]
- Two cloud copies mean two sets of services to pay for. The test copy should be small and switched off when idle. The monthly cost budget of ADR-0007 covers both.
- Decision 7 removes the independent review for the tech lead's own changes, including the pipeline, the safety folders and the live release. Nobody else checks AI-written code before it merges, so the tests, the 80% gate, the scanning and the tech lead's own careful review are the safety net. Honest downsides: (a) the firmware signing key stays in the pipeline (ADR-0005 decision 4) but its second-person safeguard no longer applies to the tech lead, so one stolen or compromised GitHub account could sign firmware for customer devices; moving the key offline, or protecting the account with two-factor login and a hardware security key, is strongly advised and left to the tech lead; (b) the EE's approval on safety functions, required by the SDLC playbook, is no longer enforced by GitHub for the tech lead's changes, so it becomes a working agreement; Phase 1 has no control functions and status-only reads, which limits the exposure, but Phase 2 (control) must reopen this rule; (c) a large customer's audit may ask who approved a release. ADR-0005 (decision 4 and consequences), ADR-0001, the GitHub Workflow Guide and CODEOWNERS wording need updating, and the GitHub rulesets must be changed by hand. Not yet changed. [Confirm]
- If the repository goes private on the Free plan, branch rules, CODEOWNERS, the environment approval of decision 3 and CodeQL may stop working (GitHub lists them under the paid Team plan or public repositories only; not yet verified for rulesets). Then either a paid plan is needed, or the release approval and the firmware signing key move to an offline manual step (ADR-0005 alternative). Check on a practice private repository before the switch. The pipeline is written to work either way.
- Anything ever committed to a public repository must be treated as exposed even after it goes private. The no-secrets rule of ADR-0005 stays.
- Several components share one `ci-gate`. Required checks that skip unchanged components can cause pull requests to wait forever or pass wrongly; this needs a tested design in P1-01. [Confirm]
- New stories are needed for the blueprints, the two environments, the deployment pipeline, the alerts, and the scanning set-up. Estimates need review.
- The alert delivery for customers (alarm emails or SMS from the dashboard) is separate and not decided here.

## To verify (early, in P1-01 and the early cloud test)

- Terraform or OpenTofu can create IoT Core with our own CA, the queue, the container service, S3 with Object Lock, and Cognito, and has a usable Tiger Cloud provider; choice between Terraform and OpenTofu and where the state is kept.
- GitHub OIDC to AWS works with separate test and live roles.
- GitHub environments with a required reviewer work on this repository on the current plan, and what changes if it becomes private.
- CodeQL supports Python and TypeScript on this repository, and the free plan limits for a private repository.
- Container image scanning works in the build and its High/Critical rule can be set to block.
- The shared `ci-gate` behaves correctly when only some components change (required checks and path filters).
- CloudWatch alarms can express "no data from a device for a set time", and cost of the logs at fleet size.
- Deploy and rollback times, and that a rollback does not break the database (migrations must be reversible or forward-compatible).

## Not decided here

- Repository public or private (decided later by the tech lead).
- Where the Terraform state lives, the folder layout, and the branch model for infrastructure changes (P1-01).
- Database migration tooling for the backend.
- Container registry, image naming and how backend and dashboard are versioned together.
- Alarm delivery to customers (email, SMS, push) and its service.
- Network updates of firmware (Phase 2 ADR).
- Disaster recovery targets and backup restore tests for the cloud.
- Paid scanning or monitoring vendors (only if a customer asks).

## References

- ADR-0001, ADR-0003, ADR-0005, ADR-0006, ADR-0007, ADR-0008
- GitHub Workflow Guide (rulesets, CODEOWNERS, `ci.sh` and coverage rules)
- GitHub plans page, checked 19 Nov 2026: protected branches and CODEOWNERS for private repositories are listed under the Team plan; environment approval rules are listed for public repositories on the Free plan; Actions minutes 2,000 (Free) and 3,000 (Team) a month
