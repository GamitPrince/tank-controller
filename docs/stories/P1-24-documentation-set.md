# P1-24: Write README, setup guide, runbook, CHANGELOG and Feature Completion documents

- Story ID: `[Confirm]` — not yet issued.
- Epic: E6 Documentation and release. Points: 3. Priority: Must. Component: docs. Review flag: none.
- Status: **Partly done.** The setup guide (`docs/setup-guide.md`) and the Feature Registry (`docs/features/README.md`) were added in S-052, which also took the split and the two open questions below as recommended. The runbook, onboarding note and second-person bring-up test are left for a second story once the cloud exists.

## Goal
A developer who did not build the system can bring it up and run it from the written documents.

## Phase check
Documentation only.

## What already exists
| Document | State |
| --- | --- |
| `README.md` | Exists, but its folder table is out of date: it still describes `gateway/` as "Modbus, MQTT, OPC UA" and says `interfaces/` needs "all three developers" |
| `CONTRIBUTING.md` | Exists and is current after S-010 |
| `CHANGELOG.md` | Exists and current as of S-010 and S-011 |
| `docs/github-setup.md` | Exists, serves as the repository setup guide, but **still lists ArkinGamit and SHINE-18** and the old `INTERFACE_REVIEWERS` value |
| `docs/adr/` | ADR-0003 to 0009 merged; ADR-0001 Proposed; **ADR-0002 missing**; the merged ADRs' status lines are wrong |
| `docs/runbook.md` | **Missing** |
| `docs/onboarding.md` | **Missing** |
| `docs/setup-guide.md` | **Missing** as such; `github-setup.md` covers repo setup, not system bring-up |
| `docs/features/completed/` | **Empty.** Eleven stories closed, no Feature Completion Documents |
| `docs/features/README.md` (Feature Registry) | **Missing** |
| `docs/stories/` | Created by this exercise; **not yet committed** |

## Acceptance criteria (from the story card)
- All listed documents exist.
- **A developer who did not write the setup guide can bring up the simulator system by following it.** This is the real test and cannot be faked — it needs a second person to try it.
- Completed features are indexed in the **Feature Registry**.

## Dependency
Most of it can only be written once there is a system to document: the setup guide needs the simulator (P1-02), the runbook needs the cloud (P1-17). The **Feature Registry and the stale-document fixes can be done now** and would clear real debt.

## Suggested split
This 3-point story is doing too much at the end of Phase 1. Consider splitting: (a) a small chore now to fix the stale README and `github-setup.md` and create the Feature Registry; (b) the setup guide and runbook late, when there is something to bring up.

## Out of scope
Editing the RSD or the story cards — they are Claude Docs owned by the project manager.

## Open questions
- `[Confirm]` Split as above?
- `[Confirm]` Who is the second person who verifies the setup guide works?
- `[Confirm]` Do the eleven already-closed stories need back-filled Feature Completion Documents, or does the registry start from the next story?
