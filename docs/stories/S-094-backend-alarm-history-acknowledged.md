# S-094: Show acknowledgements in a tank's alarm history

- Story ID: S-094 (issue #191).
- Epic: E4, the backend half of P1-18, part 8. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency. The follow-up S-093 recommended (its `[Confirm]` 4), stacked on S-093 until S-092 and S-093 merge. Uses S-091 (the history endpoint), S-092 (the `alarm_acknowledgements` table) and S-093 (the acknowledge endpoint).

## Goal
Let the alarm history say, for each raised alarm, whether someone has acknowledged it, and who, when and with what note. The dashboard's alarm list (a later story) can then mark unacknowledged alarms and show who saw each one, from the one endpoint it already reads.

## Phase check
Phase 1, read-only. `GET /v1/tanks/{tank_id}/alarms` gains one field per event; nothing new writes anything, apart from the audit entry S-080 already writes for service. **Acknowledgements are a record for people only:** showing them changes nothing about an alarm's state, and nothing is sent to a device or touches the hardwired safety chain (AGENTS.md section 1). No AWS resource or paid service.

## Decisions already made
- **S-091:** the range, ordering, limit, `more`, `untimed`, scoping (another customer's tank answers as an unknown one) and service auditing stay exactly as they are.
- **S-092:** at most one acknowledgement per event, append-only, with `subject`, `role`, `at_unix_ms` and an optional `note`.
- **S-093:** only a `high` or `low` event still in force can be acknowledged, so only those events can ever carry one.

## Files to create or change
- `backend/tankapi/alarm_history.py`: each event gains `acknowledged`, read with an outer join on `alarm_acknowledgements`.
- `backend/tests/test_alarm_history.py`: the new field; the existing expected events gain `"acknowledged": None`.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI schema of `GET /v1/tanks/{tank_id}/alarms` gains one nullable field per event. No new path, no new method. `interfaces/` is unchanged.

## Acceptance criteria
- Each event in the history has `acknowledged`: `null` when it has none, or `{"subject": ..., "role": ..., "at": <Unix ms>, "note": <text or null>}` for the one acknowledgement S-092 holds for it.
- `acknowledged` is filled in whatever the alarm's state is now, so a raise that was acknowledged and has since cleared still shows who acknowledged it `[Confirm]` 1.
- A customer's caller sees the acknowledgements on their own tank's events, the subject included; service sees them on every tank `[Confirm]` 2. Another customer's tank still answers `404 {"detail": "not found"}`, as in S-091.
- Ordering, the limit, `more` and `untimed` are unchanged; one acknowledgement never adds or removes an event, and the query still uses one round trip for the events.
- The route stays `GET`-only and writes nothing apart from S-080's audit entry for service.

## Test plan
pytest on SQLite with made-up customers, tanks, thresholds, scans, events and acknowledgements, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: an event with no acknowledgement gives `null`; an acknowledged raise with and without a note; an acknowledged raise that has since cleared; events of another tank's acknowledgements not shown; the limit and `more` unchanged with acknowledged events in the range; a customer's own tank and a service caller both see the field; the existing S-091 tests pass with `"acknowledged": None` added.

## Out of scope
Filtering the history by acknowledged or not; a count of unacknowledged alarms; the person's display name instead of the token `sub` (the Cognito story); un-acknowledging; notifications; the dashboard alarm list; the S3 Object Lock copy; anything that commands a device or changes how an alarm is judged.

## Open questions
1. `[Confirm]` An acknowledgement stays shown after the alarm clears, because the history is a record of what happened, and "seen at 14:05 by this person" is part of it. Recommendation: keep it.
2. `[Confirm]` A customer's users see each other's acknowledgement subjects and notes on their own customer's tanks. The subject is an opaque Cognito ID until the dashboard maps it to a name. Recommendation: keep it; every user of a customer may see who on their own team acknowledged an alarm.
3. `[Confirm]` The field is always present (`null` when there is no acknowledgement) rather than left out, so the dashboard reads one shape. Recommendation: keep it.
4. `[Confirm]` Built on the S-093 branch while S-092 (#189) and S-093 (#190) are in review; once they merge, `develop` is merged into this branch (no rebase, no force-push) before review.
