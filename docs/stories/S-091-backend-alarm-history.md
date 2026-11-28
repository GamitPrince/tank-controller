# S-091: Serve a tank's alarm history from the backend

- Story ID: S-091 (issue #185).
- Epic: E4, the backend half of P1-18, part 5. Points: 1. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/` and `interfaces/` are not touched; no migration; no new dependency. Chosen by the tech lead on 28 Nov 2026. Uses S-089 (the `alarm_events` table), S-090 (ingest records the events), S-073 (customers, plants and tanks), S-075 and S-076 (token, role and customer), S-078 (scoping) and S-080 (the audit trail).

## Goal
Let a signed-in user read the alarm history of a tank they may see: each raise, clear and `cannot_evaluate` in a time range, with what was judged, so the dashboard's alarm list (a later story) has an endpoint to read.

## Phase check
Phase 1, read-only. One new `GET` route and nothing that writes, apart from the audit entry S-080 already writes for service staff. **These are advisory alarms for people, never actions:** nothing is sent to a device and nothing touches the hardwired safety chain (AGENTS.md section 1). No acknowledgement (S-092). No AWS resource, notification or paid service (ADR-0007's three gates still hold).

## Decisions already made
- **ADR-0008 decision 3 and S-078:** the backend checks every request; a customer's caller sees only their own customer's data, and something they may not see answers exactly as something unknown, so IDs cannot be probed. Service sees everything and every service request is audited (S-080).
- **S-072:** a range is `[from, to)` in Unix seconds, bounded by a constant, and untimed data is counted, never stamped with its arrival time.
- **S-089:** one event per change of state, at the scan's time, with the threshold row, limit and deadband in force.
- **AGENTS.md section 7:** a value that could not be judged comes back with no value, never a substitute.

## Files to create or change
- `backend/tankapi/alarm_history.py` (new): `GET /v1/tanks/{tank_id}/alarms`.
- `backend/tankapi/main.py`: mounts the router under `/v1`.
- `backend/tankapi/audit.py`: records the `tank_id` path parameter and the `limit` query parameter in an entry's selection.
- `backend/tests/test_alarm_history.py` (new); `backend/tests/test_health.py` (the OpenAPI path list).
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
The OpenAPI document gains one `GET` path. `interfaces/` is unchanged.

## Acceptance criteria
- `GET /v1/tanks/{tank_id}/alarms?from=<t>&to=<t>&limit=<n>` returns the events of the tank's thresholds whose `t` is in `[from, to)`, **newest first** `[Confirm]` 1, ties in the order they were recorded (newest row first).
- Each event gives its ID, `t`, the threshold row ID with its measure, signal, direction and class, the limit and deadband in force, the state, and either the value judged with the reading's quality, or the reason it could not be judged and no value.
- `from < to <= from + 31 days` `[Confirm]` 2; `limit` is 1 to 1000 and defaults to 1000. When more events are in the range, the newest `limit` come back and `more` is true `[Confirm]` 3. A bad tank ID, range or limit is a 422.
- An event with no time (an untimed scan) is left out of every range and counted in `untimed` `[Confirm]` 4.
- An empty history is `200` with an empty list.
- A customer's caller sees only tanks of their customer. Another customer's tank and an unknown tank both answer `404 {"detail": "not found"}`. Service sees every tank, and the audit entry records the tank ID with the range and limit. A customer's request is not audited (S-080).
- The route has only `GET`; nothing here writes plant data or sends anything to a device.

## Test plan
pytest on SQLite with made-up customers, tanks, thresholds, scans and events, locally on Windows and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: an empty history; ordering newest first, with ties; the range ends and another tank's events left out; the limit and `more`; an untimed event counted; a customer's own tank; another customer's tank and an unknown tank refused alike; service on any tank, audited with the tank ID; a customer not audited; an unknown tank for service; bad tank IDs, ranges and limits; the widest range; no token; no `POST`.

## Out of scope
Acknowledgement (S-092); the current state of each alarm at the start of a range; paging by cursor; filtering by state, class or signal; notifications; the dashboard alarm list; an admin endpoint for thresholds; the S3 Object Lock copy; the TimescaleDB container, Cognito, Docker and Terraform; anything that commands a device.

## Open questions
1. `[Confirm]` Newest first, because an alarm list shows the latest at the top. The readings endpoint is oldest first for trends; the two differ on purpose. Recommendation: keep it.
2. `[Confirm]` A 31-day range per request, so one call covers a month's alarm list. Events change only on a change of state, so a month is small next to a month of readings. Recommendation: keep it until real event rates are known.
3. `[Confirm]` Up to 1000 events per call, the newest kept, with `more` instead of a 422 (the readings endpoint refuses an over-full range). An alarm list wants the newest; the client narrows `to` to the oldest `t` shown to read further back. Events at that very second may then repeat, so a cursor is a later story if it is needed.
4. `[Confirm]` Untimed events are counted for every caller, customers included. Unlike readings (S-078), each event is already the tank's own, judged against that tank's thresholds, so the count shows nothing of another customer.
5. `[Confirm]` The audit entry's selection now carries `tank_id` and `limit`, because without them a service read of a tank's alarms would not say which tank. `device_id` stays null for this route.
