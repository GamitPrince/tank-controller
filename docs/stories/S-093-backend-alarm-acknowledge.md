# S-093: Acknowledge an alarm in the backend

- Story ID: S-093 (issue #188).
- Epic: E4, the backend half of P1-18, part 7. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency. The second half of the tech lead's "alarm acknowledgement" (28 Nov 2026), stacked on S-092 (the table). Uses S-089 and S-090 (the alarm events), S-091 (the history endpoint and its scoping), S-075 and S-076 (token, role and customer) and S-080 (the audit trail).

## Goal
Let a customer's user say "I have seen this alarm": acknowledge one raised alarm event through the backend, recorded once in S-092's table with who did it and the server's time, so the dashboard's alarm list (a later story) can offer it.

## Phase check
Phase 1. One new `POST` route that writes one `alarm_acknowledgements` row, and nothing else. **An acknowledgement is a record for people only:** it never sends anything to a device, never clears, silences or mutes an alarm and never changes how S-088 judges or S-090 records one. These are advisory cloud alarms, never trips or interlocks, and nothing touches the hardwired safety chain (AGENTS.md section 1). Plant data stays read-only. No AWS resource, notification or paid service.

## Decisions already made
- **ADR-0008 decision 3, S-078, S-091:** the backend checks every request; a customer's caller sees only their own customer's tanks, and something they may not see answers exactly as something unknown (`404 {"detail": "not found"}`). Every service request is audited, refused ones included (S-080).
- **S-092:** one append-only row per acknowledged event, roles operator, maintenance and admin only, at most one per event, a note of at most 200 characters.
- **S-088:** a value that cannot be judged (`cannot_evaluate`) never clears a raised alarm.

## Files to create or change
- `backend/tankapi/alarm_acknowledge.py` (new): `POST /v1/alarms/{event_id}/acknowledgement`.
- `backend/tankapi/alarm_history.py`: its tank check made public (`tank_visible`) and shared.
- `backend/tankapi/main.py`: mounts the router.
- `backend/tankapi/audit.py`: records the `event_id` path parameter in an entry's selection.
- `backend/tests/test_alarm_acknowledge.py` (new); `backend/tests/test_health.py` (the OpenAPI path list).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI document gains one `POST` path. `interfaces/` is unchanged; nothing reaches a device.

## Acceptance criteria
- `POST /v1/alarms/{event_id}/acknowledgement` with a JSON body `{"note": <optional text>}` adds one `alarm_acknowledgements` row with the event ID, the caller's `sub` and role, the server time in Unix milliseconds and the note, and answers `201` with `event_id`, `subject`, `role`, `at` and `note`. The time never comes from the client.
- Operator, maintenance and admin may acknowledge an alarm of their own customer's tank. Service gets `403 {"detail": "not allowed"}`, and the attempt is audited with the event ID `[Confirm]` 1.
- An unknown event and another customer's event both answer `404 {"detail": "not found"}`.
- Only a raise still in force can be acknowledged: an event in state `high` or `low` with no later judged event (`normal`, `high` or `low`) of the same threshold, "later" by scan time and then recording order, as in S-091. Otherwise `409 {"detail": "alarm not raised"}`: a `normal` or `cannot_evaluate` event, or a raise since cleared or replaced. A later `cannot_evaluate` does not stop it `[Confirm]` 2.
- A second acknowledgement answers `409 {"detail": "already acknowledged"}` and adds nothing; the table's unique key decides a race.
- `note` is optional, 1 to 200 characters. An empty, over-long or non-string note, an unknown field, a body that is not a JSON object or no body at all is `422`, and so is a bad event ID `[Confirm]` 3.
- Acknowledging writes nothing else: no `alarm_events` row, no threshold, nothing to a device. S-091's history is unchanged `[Confirm]` 4.

## Test plan
pytest on SQLite with made-up customers, tanks, thresholds, scans and events, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: success for each customer role with the subject, role, server time and note; no note, with the events unchanged; service refused and audited; another customer's event and an unknown event refused alike; a second acknowledgement; a cleared, replaced, `normal` and `cannot_evaluate` event refused; a raise followed only by `cannot_evaluate` accepted; bad bodies, no body and bad event IDs; the longest note; no token; a race lost at the unique key; the OpenAPI paths.

## Out of scope
Showing acknowledgements in S-091's history (a follow-up story, `[Confirm]` 4); un-acknowledging; acknowledging by tank or in bulk; the user's display name; notifications; the dashboard alarm list; the S3 Object Lock copy; the TimescaleDB container, Cognito, Docker and Terraform; anything that commands a device or changes how an alarm is judged.

## Open questions
1. `[Confirm]` Who may acknowledge: operator, maintenance and admin of the tank's customer; **service is refused**. An acknowledgement says the site's people have seen the alarm, and our staff acknowledging for them would hide that. Service still reads every alarm (S-091), and its refused attempt is audited. Recommendation: keep it.
2. `[Confirm]` Only a raise still in force, so an acknowledgement always means "seen while it was raised". Acknowledging an alarm that has already cleared is refused rather than recorded late. Recommendation: keep it; the history shows clears anyway.
3. `[Confirm]` A body is required, `{}` at least, so the route has one shape; a missing body is 422. Recommendation: keep it.
4. `[Confirm]` S-091's history does not yet show acknowledgement. Recommendation: a small follow-up story adds `acknowledged` (who, when, note, or null) to each event of the history.
5. `[Confirm]` The acknowledgement commits before the service audit entry would be written, but service is refused before anything is written, so a failed audit write (503, S-080) never hides a recorded acknowledgement. If service is ever allowed, the two writes must share one transaction.
