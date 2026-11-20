# P1-18: Threshold alarms in Critical, Warning and Advisory classes, with acknowledgement and audit trail

- Story ID: `[Confirm]` — not yet issued.
- Epic: E4. Points: 5. Priority: Must. Component: dashboard (backend). Review flag: none.

## Goal
Values crossing configured thresholds raise classified alarms that an operator can acknowledge, with a tamper-proof history.

## Phase check
Phase 1. **Threshold alarms only — no analytics**, as the card itself states. No prediction, no trend-based alarms, no AI recommendations (Phases 2 to 4).

**Safety boundary:** an alarm is a notification, never an action. **No alarm writes to any device**, and acknowledgement travels no further than the cloud. The hardwired safety chain acts on its own, independently; a Critical alarm here is a report that a trip happened, not a cause of one.

## Decisions already made
- **ADR-0008:** audit trail is an **append-only table plus a daily write-once S3 copy with Object Lock**; roles are operator, maintenance, admin and service; the backend checks every request; the browser never talks to the broker.
- **ADR-0007:** calculation version stored; retention rules apply to alarm history too `[Confirm]`.
- `AGENTS.md`: failed sensors are flagged and excluded, never silently replaced — so a failed sensor must not generate threshold alarms from a bad value.

## Acceptance criteria (from the story card)
- Each alarm records class, time, acknowledgement and **who** acknowledged it.
- Alarm history **cannot be edited** — satisfied by the append-only table plus Object Lock copy.
- Thresholds are **configurable** (no hardcoded values).
- **No alarm writes to any device.**
- Plus: an alarm raised from a value whose quality flag is bad, or whose age exceeds the staleness limit, is suppressed or marked as such rather than shown as a live plant condition.

## Test plan
pytest: threshold crossed, cleared, re-crossed, acknowledged by each role, acknowledgement attempted by a role without permission, alarm from a stale or failed-sensor value, attempt to edit history, Object Lock copy written. Confirm no code path from alarm handling reaches a device publish.

## Dependency
P1-17 (storage) and P1-20 (roles, so "who acknowledged" means something).

## Out of scope
SMS or email notifications — the card's question 9 assumes not needed in Phase 1 and no story exists `[Confirm]`. Sensor mismatch, time-to-high-level and stratification flags (Phase 2). Any automatic response.

## Open questions
- `[Confirm]` Threshold values and who sets them: per tank, per customer, or global defaults?
- `[Confirm]` Which roles may acknowledge which classes?
- `[Confirm]` Retention for alarm history — forever, or the per-second 90-day rule?
- `[Confirm]` Are notifications wanted after all?
