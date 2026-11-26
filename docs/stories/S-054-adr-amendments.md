# S-054: Amend the ADRs for the 26 Nov 2026 decisions

- Story ID: S-054 (issue #111).
- Epic: P1-00 (tech stack and ADRs). Points: 1. Priority: Must. Component: docs. Review flag: one collaborator other than the author.

## Goal
The ADRs say what was decided on 26 Nov 2026 (recorded in S-053), so a reader of an ADR is not sent the wrong way by text that has been overturned.

## Phase check
Phase 1, documentation only. No code, no interface, no safety path.

## Decisions already made
All content comes from the tech lead's review of 26 Nov 2026, recorded in `docs/stories/S-053-record-26-nov-decisions.md`. Nothing new is decided here.

## Approach
Merged ADRs are not rewritten. Each affected ADR keeps its text and gets:
- a status-line note: "Amended on 26 Nov 2026 by the tech lead (S-054); see Amendments at the end";
- an **Amendments (tech lead, 26 Nov 2026, S-054)** section at the end, numbered, each item naming the decision it changes. Where an amendment and the original text disagree, the amendment wins.

ADR-0001 is still Proposed, so it is revised in place and stays Proposed until a collaborator other than the author approves it.

## Files to change
- `docs/adr/ADR-0003`: shared link library in `shared/link-protocol/`, cppcheck blocking, Zephyr caching, acquisition timing and boot-time logging.
- `docs/adr/ADR-0004`: mass removed from decision 10, Modbus and OPC UA void, the library location, MQTT topic and batching, independent startup, `gateway/` removed.
- `docs/adr/ADR-0006`: the library location, publishing, the first cloud test device.
- `docs/adr/ADR-0007`: hosting now and later, and the state of the three gates (customer confirmation outstanding; IoT Core test approved, free allowances and credits only; Tiger Cloud trial for development, Scale target, no paid plan before sizing); mass removed.
- `docs/adr/ADR-0008`: owners, `backend/` location, Alembic migrations, one-approval review of the coverage exclusion list.
- `docs/adr/ADR-0009`: rule 7 reversed (no bypass list), public repository, Terraform folder and state, GitHub Container Registry and tags, CI checks.
- `docs/adr/0001-public-repository-on-github-free.md`: revised. Public and private split, authority without bypass, options considered, deciders.
- `AGENTS.md`, `CHANGELOG.md`: pointers.

## Out of scope
ADR-0002 (the EE's; not written here). ADR-0005 needs no change: the reversal of ADR-0009 rule 7 restores its signing safeguard, which ADR-0009's amendment states. The RSD and the Workflow Guide (the project manager's documents).

## Acceptance criteria
- Each of the six ADRs has the status-line note and the Amendments section, and every S-053 decision that touches an ADR appears in one.
- ADR-0001 says Proposed and does not claim acceptance.

## PR checklist notes
Title `docs(docs): amend the ADRs for the 26 Nov 2026 decisions (S-054)`, branch `feature/S-054-adr-amendments`, `Closes #111`. No `safety` label.
