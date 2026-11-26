# S-050: Refresh the project status after S-047 to S-049

- Story ID: S-050 (issue #103).
- Epic: none (repo documentation). Points: 1. Priority: Should. Component: docs. Review flag: none.

## Goal
The two places agents and people read for "where are we" match the repository again: the Phase 1 status table in `docs/stories/README.md` and `AGENTS.md` section 10, last refreshed on 25 and 21 Nov 2026.

## Phase check
Documentation only. No code, no interface, no safety path.

## Decisions already made
- The ESP32 firmware lives in `esp32/` (S-047). The FRDM-to-ESP32 UART driver (S-048) and the uplink service thread (S-049) are merged.
- The RSD and story cards are the project manager's Claude Docs and are not edited here (AGENTS.md section 11).

## Files to change
- `docs/stories/README.md`: the date line, the P1-12 row (FRDM half done; what is left), and backlog item 3, which still says the ESP32 firmware has no story.
- `AGENTS.md`: the "last updated" line and section 10 (state, what is not done, what waits on people, the order of work).

## Interfaces touched
None.

## Acceptance criteria
- The P1-12 row lists S-042 to S-049 as done and leaves only the ESP32 Wi-Fi, TLS, MQTT and 4G code, the board overlay and the broker.
- AGENTS.md section 10 names what is built (all Phase 1 plant reads, the flash log, the UART link both ends, the uplink thread), what is not, and what waits on people, with no stale "next" step.
- No other section of AGENTS.md changes. `docs-links` passes.

## Test plan
`docs-links` CI check; read both files against `gh pr list --state merged`.

## Out of scope
The seven ADR status lines (S-051), the runbook and Feature Registry (S-052), any decision in the pending list.

## Open questions
None.

## PR checklist notes
Title `docs(docs): refresh the project status after S-047 to S-049 (S-050)`, branch `feature/S-050-refresh-project-status`, `Closes #103`.
