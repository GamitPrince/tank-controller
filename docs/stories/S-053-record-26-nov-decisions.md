# S-053: Record the 26 Nov 2026 Phase 1 decisions

- Story ID: S-053 (issue #109).
- Epic: none (project records). Points: 1. Priority: Must. Component: docs. Review flag: one collaborator other than the author.

## Goal
The tech lead's decision review of 26 Nov 2026 (29 items) is written into the repository's standing brief (`AGENTS.md`) and the story pages, so nobody works from a decision that has been overturned.

## Phase check
Phase 1, documentation only. No code, no interface, no safety path.

## Decisions recorded (tech lead, 26 Nov 2026)
1. **Dashboard owner:** GamitPrince owns P1-21, P1-22, P1-23 and P1-26.
2. **P1-11 (Modbus RTU and TCP) is VOID** for Phase 1. No replacement work. A future need is a new scope decision and story.
3. **P1-13 (OPC UA) is VOID**, not deferred. No customer requirement was found. Same rule for a future need.
4. **`gateway/` is removed** with every reference to it. The `.github/` changes this needs (CI job, CODEOWNERS, templates, the `gateway` title scope) are authorised for that story only. Not a general permission to change rulesets.
5. **Acquisition:** one consolidated flash record per second. PT100 sampled every 1 s, analog every 100 ms, digital inputs asynchronous with a 10 ms response target (the debounce times stay 200 ms and 5 s). Planning assumption: 86,400 records a day, to be checked against the real record size and usable flash. **Startup:** the FRDM starts acquiring and logging to flash after hardware initialisation whether or not a network is up; the ESP32 connects on its own, and buffered records go out once it is connected.
6. **MQTT:** topic `tank/{device_id}/records`; a batch every 5 s (five one-second records); buffered records replayed oldest first; sequence numbers, CRC and delivery confirmation kept; unacknowledged records kept and resumed after reconnect; each device publishes only to its own topic.
7. **Backend** in the repository-root `backend/` folder (Python, FastAPI), separate from `dashboard/`.
8. **Terraform** in `infrastructure/terraform/`: S3 remote state with S3's native lock file, separate test and production state and resources, encryption, versioning and restricted IAM. State is never committed.
9. **Migrations:** Alembic with SQLAlchemy, under `backend/migrations/`, tested before production; a destructive change needs review, a backup and a rollback plan.
10. **Container registry:** GitHub Container Registry. Images tagged with the semantic version and the commit SHA; release tags never overwritten.
11. **ADR-0001:** the repository stays public. Approved source and documentation may be public. Proprietary hardware design, safety evidence and confidential customer information stay private. ADR-0001 is revised and submitted for acceptance (S-054); it is not Accepted until approved.
12. **No ruleset bypass list.** The tech lead is not exempt. This reverses ADR-0009 rule 7 (amended in S-054).
13. **QA owner:** prinz-assists, independent of the author. The EE handles safety and hardware validation. GamitPrince gives final Phase 1 acceptance.
14. **Multi-PR stories:** one issue per PR. Split larger work into smaller stories, link them with milestones or a parent issue, and never weaken `pr-policy`.
15. **CI:** cppcheck errors become blocking, with reviewed severities and suppressions, and the Zephyr tree is cached, keyed on the Zephyr version, the manifest and the dependency lock. One dedicated story.
16. **Shared link library** moves to `shared/link-protocol/` before the ESP32 work grows; the FRDM and the ESP32 build the same code.
17. **Hosting:** Tank-AI-managed SaaS in Tank-AI's AWS account now, with tenant isolation. Dedicated deployments in customers' AWS accounts are a final-phase target, not current scope. Written Siemens/Astec confirmation is still outstanding: ADR-0007's first gate is not passed.
18. **AWS IoT Core proof of concept:** approved for one test ESP32-S3 + A7672S device, non-production, free allowances and credits only, with billing alerts. Not yet run. This is ADR-0007's second gate.
19. **Tiger Cloud:** free services or the trial for development and testing; Scale is the production target subject to sizing; no paid plan until sizing and cost are reviewed. Account eligibility not yet checked. This is ADR-0007's third gate.
20. **Hardware:** the 24 V to 5 V converter, the two 4-20 mA inputs, the six PT100s with their MAX31865s and the 16 digital inputs at 24 V DC were reported tested and EE-approved. The analog path is still the AD4111 (confirmed 26 Nov 2026). The test records stay private, never in this repository.
21. **PT100 range:** 0 to 200 °C on all six channels (already enforced as `out-of-range` in firmware).
22. **Integration:** sensors connected to the FRDM; FRDM-to-ESP32 end-to-end testing remains.
23. **Density table removed from Phase 1.** S-037 (issue #77) is closed as not planned. No density-based mass calculation in Phase 1; volume stays.
24. **No other client dependencies** were identified.
25. **Review rule unchanged:** one approval from a collaborator other than the author, also for `interfaces/` (confirmed 26 Nov 2026; the checklist's "all three developers" line was old story-card wording).

## Files to change
- `AGENTS.md`: section 2 (owners, authority), section 3 (no bypass list), section 4 (summary notes), section 5 (range, hardware status), section 6 (layout answers), section 10 (state).
- `docs/stories/README.md`: status rows for P1-04, P1-11, P1-13, P1-21 to P1-23, P1-26; totals; backlog notes.
- `docs/stories/P1-04-radar-level.md`, `P1-11-field-polling.md`, `P1-13-opc-ua.md`, `S-035-cloud-level.md`: a status note at the top. S-035's mass sections are rewritten when the backend story builds it.
- `CHANGELOG.md`.

## Out of scope
The ADR text (S-054). Removing `gateway/` (S-055). Any code. The RSD and the story cards (the project manager's Claude Docs). The hardware test records (private).

## Acceptance criteria
- No page in `AGENTS.md` or `docs/stories/` still calls P1-11, P1-13, the dashboard owner, the QA owner, the backend location, Terraform's location, the migration tool, the registry, the topic or the batch interval open.
- S-037 is closed with a comment pointing at this story.

## PR checklist notes
Title `docs(docs): record the 26 Nov 2026 Phase 1 decisions (S-053)`, branch `feature/S-053-record-26-nov-decisions`, `Closes #109`. No `safety` label.
