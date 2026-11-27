# Phase 1 story specs

One spec per story from **Tank-AI — Phase 1 Story Cards** (26 Oct 2026, 27 stories, 107 points, four 2-week sprints). Each file follows the spec format in `AGENTS.md` section 9.

## How to use these

- One story per session. Read `AGENTS.md` first, then the one spec.
- Create the GitHub issue before any work; no story card, no work.
- A spec is not authority on its own. Where a spec and an ADR disagree, the ADR wins and the spec says so in its **Conflicts with the ADRs** section. Stop and ask rather than guessing.

## Story ID naming `[Confirm]`

Files are named by the story card's temporary `P1-xx` IDs, not `S-0xx`. Section 7 question 1 of the story card leaves the real IDs open, and inventing 26 S-numbers now would fix an order that the conflicts below are likely to change. **The next free story ID is S-012** (S-001 to S-011 are used). When a story starts, create its issue as `S-0xx: <title>`, then rename its spec file to match.

### Already-used IDs

| ID | Issue | What it was |
| --- | --- | --- |
| S-001 | #1 | Practice pull request |
| S-002 | #3 | Phase 1 ADRs (this is **P1-00**) |
| S-003 to S-009 | #4 to #10 | One per ADR, ADR-0003 to ADR-0009 |
| S-010 | #18 | Fix review rules for the current team |
| S-011 | #21 | Align AGENTS.md with the S-010 review rule |

## Status against the story card

Updated 27 Nov 2026 (S-081) from the merged pull requests up to S-080; the tech lead's decision review of 26 Nov 2026 is `S-053-record-26-nov-decisions.md`. "S-0xx" is the story issue that delivered the work.

| ID | Story | Pts | Status | Note |
| --- | --- | --- | --- | --- |
| P1-00 | Tech stack and ADRs | 5 | **Partly done** | ADR-0003 to 0009 merged (S-003 to S-009); the four firmware layers build in CI (CHORE-01, S-015). Merged ADRs' status lines say Accepted (S-051), with amendments for the 26 Nov 2026 decisions (S-054). ADR-0002 unwritten (EE), ADR-0001 still Proposed |
| P1-01 | Repo, protection, PR template, CI skeleton | 3 | **Done** | Residual `ci.sh` work done as **CHORE-01** (S-015) |
| P1-02 | Simulator | 5 | **Done** (S-018) | Every signal in the list, fault injection, outage replay with original timestamps |
| P1-03 | Signal list v1 | 3 | **Done** (S-017) | `interfaces/signals-v1.yaml` and `records.cddl`; PT100 class and channel 16 recorded in S-023 |
| P1-04 | Radar level, volume, mass | 5 | **Partly done** | Firmware reads radar and pressure 4-20 mA (S-034). Level % and volume move to the cloud (ADR-0004 decision 10): specced in S-035 and S-036; the calculation itself is built locally (S-082), its table storage, editing and wiring are not. **Density-based mass removed from Phase 1** (26 Nov 2026); S-037 closed |
| P1-05 | HH and LL switch status | 3 | **Done** (S-022) | Channels 1 and 2, normally closed, 200 ms, in `firmware/src/safety/` |
| P1-06 | Multi-zone PT100 | 5 | **Done** (S-032) | Six sensors, 2 upper / 2 middle / 2 bottom at 180 degrees, read independently |
| P1-07 | Heater and thermal-oil temps | ~~3~~ | **VOID** | No thermal oil, no spare PT100s. Points returned |
| P1-08 | Ambient and wind | ~~2~~ | **VOID** | No ambient sensor, no wind sensor. Points returned |
| P1-09 | Alarm and trip status | 3 | **Done** (S-031) | Channels 10 to 15. **Scope cut: no over-temp, e-stop or fire/gas** |
| P1-10 | Prove no write path to the safety chain | 2 | Not started | EE. **Record cannot live in this public repo** |
| P1-11 | Poll over 4-20 mA, Modbus RTU and TCP | ~~5~~ | **VOID** (26 Nov 2026) | Modbus RTU and TCP excluded from Phase 1; the 4-20 mA part is done in P1-04. Points returned |
| P1-12 | Publish over MQTT | 3 | **In progress** | FRDM half done: UART link frames (S-042), delivery confirmation (S-043), CBOR records (S-044), flash log forwarded over the link (S-045), the Zephyr UART driver (S-048), the uplink service thread (S-049), the link library in `shared/link-protocol/` (S-056), the scan record, scan thread and application (S-058 to S-060), the uplink wired in with the factory device ID (S-061), up to five records per frame as one batch message (S-062, S-063) and sending at once on a change (S-065). ESP32 end of the link in `esp32/` (S-047) and its batch publisher logic (S-064). Left: the ESP32's ESP-IDF glue (MQTT client with the device certificate, Wi-Fi, 4G and failover; needs the real board), the FRDM board overlay (waits on the EE's pin mapping) and a broker, which waits on the cloud gates |
| P1-13 | OPC UA | ~~5~~ | **VOID** (26 Nov 2026) | Not deferred: no customer requirement found. A future need is a new story. Points returned |
| P1-14 | Buffer through an outage | 5 | **Done** (S-039, S-040, S-041) | FRDM flash log (ADR-0004 decision 12); a gap record tells the cloud about scans lost to a full log; 24 h outage fits the confirmed 8 MB W25Q64JV; the scan thread logs one record a second from boot, network or not (S-058 to S-060) |
| P1-15 | Clock sync | 2 | **Done** (S-038) | SNTP plus boot-relative time with boot id and "time not yet known" flag (ADR-0004 decision 11) |
| P1-16 | Remote access with no inbound ports | 3 | Not started | Rescoped: ADR-0005 says no VPN in Phase 1, so the story proves outbound-only access instead |
| P1-17 | Cloud ingest and retention | 5 | **In progress** (local only) | Backend built and tested locally: decode, store and ingest one MQTT message, query readings (S-066 to S-072, rows below). No broker, queue, TimescaleDB, retention or cloud account: **blocked by the three gates in ADR-0007** |
| P1-18 | Threshold alarms with audit trail | 5 | **In progress** (local only) | Backend side, split in five: thresholds stored per tank with history (S-087, done) and a value judged against one (S-088, in review). Left: alarm events from stored readings (S-089), the read endpoint (S-090), acknowledgement (S-091), the S3 Object Lock copy and the screen |
| P1-19 | Stale-data flag | 3 | Not started | Quality and age already travel in every record (S-017, S-044); the cloud and dashboard side is left |
| P1-20 | Role-based login | 5 | **In progress** (local only) | Backend side built locally: ownership tables and owner helper (S-073, S-074), Cognito-style token check with role and customer (S-075, S-076), readings limited to the caller's customer (S-077, S-078), service access audited (S-079, S-080). Left: the Cognito user pool, its groups and pre-token-generation trigger, and the daily S3 Object Lock audit copy; both follow the cloud gates |
| P1-21 | Main tank screen | 8 | Not started | Signal conflict **resolved**: heater, pump, valve and motor status all exist. Owner GamitPrince |
| P1-22 | Colour code with text | 3 | Not started | Dashboard. Owner GamitPrince |
| P1-23 | Trends, CSV, PDF | 5 | Not started | Should, may slip. Dashboard. Owner GamitPrince |
| P1-24 | Docs set and Feature Registry | 3 | **Partly done** | Setup guide and Feature Registry added (S-052); runbook, onboarding and the second-person check of the guide left |
| P1-25 | Bench FAT and `sys-v0.1.0` | 5 | Not started | Needs hardware and everything above |
| P1-26 | Figma screen designs | 3 | Not started | Owner GamitPrince |
| P1-27 | Valve, pump, motor and heater status | 3 | **Done** (S-033) | **Not on the story card.** Added 20 Nov 2026; channels 3 to 9, normally open, 5 s |

**Totals.** Of 110 points across these 28 rows, 15 are void (P1-07, P1-08, P1-11, P1-13), leaving **95 live points**. **32 are done** (P1-01, 02, 03, 05, 06, 09, 14, 15, 27); P1-00, P1-04, P1-12 and P1-24 (16 points) are part done, and P1-17 and P1-20 (10 points) are in progress locally. What is left waits mostly on the cloud gates (P1-17, 18, 20, and the cloud halves of P1-04, 12 and 19; backend and dashboard code can still be built and tested locally) and on bench integration (P1-25).

## Repo chores

Not on the story card. Repo infrastructure identified while working through Phase 1.

| ID | Chore | Pts | Status | Note |
| --- | --- | --- | --- | --- |
| CHORE-01 | Component `ci.sh` scripts and minimal skeletons | 5 | **Done** (S-015) | `firmware/` and `simulator/` only. Firmware job runs in about 3 minutes, so the 15-minute timeout stood. cppcheck left advisory and Zephyr-tree caching not added — both need a workflow change, so each is its own story; both done in S-057 |
| CHORE-02 | Rename `gitattributes` to `.gitattributes` | 2 | **Done** (S-025) | A pure rename: the blob hash did not change and all 131 tracked blobs were already LF, so `--renormalize` produced nothing. `git check-attr text eol -- firmware/ci.sh` now reports `set` and `lf`, and the working tree went from 116 CRLF files to 0. An older checkout keeps CRLF until re-checked-out |
| CHORE-03 | `pr-policy` reads labels from the event payload | 1 | **Specced** (S-024), not started | Spec: [`CHORE-03-pr-policy-label-source.md`](CHORE-03-pr-policy-label-source.md). Observed on PR #46: the `opened` event fires before `gh pr create` attaches the labels, so the first run demands a `safety` label that is present, and a re-run replays the same payload and fails again. Edits a CODEOWNERS policy file, so the tech lead decides first |
| S-055 | Remove `gateway/` | 1 | **Done** (S-055) | Spec: [`S-055-remove-gateway.md`](S-055-remove-gateway.md). The folder, its CI job, the `gateway` title scope in `pr-policy`, the template options and the docs that offered it (ADR-0004 decision 1) |
| S-057 | cppcheck blocking and the Zephyr tree cached | 2 | **Done** (S-057) | Spec: [`S-057-cppcheck-and-zephyr-cache.md`](S-057-cppcheck-and-zephyr-cache.md). Errors, warnings and portability findings block the firmware job; style and performance findings are shown only. The west-fetched Zephyr tree is cached, keyed on `firmware/west.yml` and `firmware/requirements-dev.txt` with no fallback key |
| S-066 | Backend skeleton in `backend/` | 2 | **Done** (S-066) | Spec: [`S-066-backend-skeleton.md`](S-066-backend-skeleton.md). FastAPI with `GET /health` only, `backend/ci.sh` and a `backend` CI job. Groundwork for P1-17; no database, ingest or cloud account |
| S-067 | Decode the CBOR batch message in the backend | 2 | **Done** (S-067) | Spec: [`S-067-backend-batch-decode.md`](S-067-backend-batch-decode.md). `tankapi.records.decode_message`: typed scan and gap records from one MQTT message, malformed input refused with a reason. Groundwork for P1-17; nothing stored |
| S-068 | Backend database schema and first migration | 2 | **Done** (S-068) | Spec: [`S-068-backend-db-schema.md`](S-068-backend-db-schema.md). SQLAlchemy models and Alembic revision 0001 for scan records and readings, with check constraints matching the decoder and a unique device, boot ID and sequence. Gap-record table split to S-069; nothing written to the database yet |
| S-069 | Gap-record table in the backend database | 1 | **Done** (S-069) | Spec: [`S-069-backend-gap-table.md`](S-069-backend-gap-table.md). `GapRow` and Alembic revision 0002: `lost` and both lost-scan marks, with check constraints matching the decoder. Split out of S-068; nothing written to the database yet |
| S-070 | Store decoded records in the backend database | 2 | **Done** (S-070) | Spec: [`S-070-backend-store-records.md`](S-070-backend-store-records.md). `tankapi.store.store_message`: the records of one message in one transaction, all or none; already-stored scans (device, boot ID, sequence) and identical gaps skipped and counted. Groundwork for P1-17; no ingest, no migration |
| S-071 | Ingest one MQTT message in the backend | 2 | **Done** (S-071) | Spec: [`S-071-backend-ingest-handler.md`](S-071-backend-ingest-handler.md). `tankapi.ingest.ingest_message`: checks the topic is `tank/{device_id}/records`, decodes, refuses a message with any record from another device, stores the rest with `store_message`; refusals logged without the payload and nothing written. Groundwork for P1-17; no broker, queue or dead-letter store |
| S-072 | Query stored readings by signal and time range | 3 | **Done** (S-072) | Spec: [`S-072-backend-readings-query.md`](S-072-backend-readings-query.md). `GET /v1/devices/{device_id}/readings?signal=&from=&to=`: one signal's stored readings in a range of up to one hour, each with quality and age, faulted ones without a value; overlapping gaps returned as gaps; unknown-time scans counted, not placed. Read-only, unauthenticated, local only until login. Groundwork for P1-17 and P1-23; no migration |
| S-073 | Customer, plant, tank and device tables | 2 | **Done** (S-073) | Spec: [`S-073-backend-ownership-tables.md`](S-073-backend-ownership-tables.md). Alembic revision 0003: customers, plants, tanks, devices and dated device-to-tank assignments (history kept, one open per device). The read helper that resolves a device to its owner is split to the next story. Groundwork for P1-20; no endpoint, no write API, record tables unchanged |
| S-074 | Resolve a device to its tank, plant and customer | 1 | **Done** (S-074) | Spec: [`S-074-backend-device-owner.md`](S-074-backend-device-owner.md). `tankapi.ownership`: `owner_now` and `owner_at` return a device's customer, plant and tank, or say it is unclaimed at that time or unknown; start included, end excluded; overlapping assignments raise; an untimed scan is never placed. Read-only, no endpoint, no migration; for P1-20 |
| S-075 | Check a Cognito-style token on every /v1 request | 3 | **Done** (S-075) | Spec: [`S-075-backend-token-check.md`](S-075-backend-token-check.md). `tankapi.auth.require_caller` on every `/v1` route: a Cognito access token, RS256 only, checked against a configured JWKS for issuer, expiry, not-before, app client and `token_use`; 401 with `WWW-Authenticate: Bearer` otherwise, 503 while unconfigured; `/health` open. Role and customer split to S-076; no per-customer scoping yet, so local only. Groundwork for P1-20; no migration |
| S-076 | Read the caller's role and customer from the token | 2 | **Done** (S-076) | Spec: [`S-076-backend-role-customer.md`](S-076-backend-role-customer.md). `require_caller` also returns the role (exactly one of operator, maintenance, admin, service in `cognito:groups`; other groups ignored) and the customer (`custom:customer_id`, positive decimal digits; none for service); otherwise 403 with a fixed body. All four roles read readings. No scoping, per-role rules or service audit yet, so local only. Groundwork for P1-20; no migration |
| S-077 | Find when a device was on a customer's tanks | 1 | **Done** (S-077) | Spec: [`S-077-backend-customer-windows.md`](S-077-backend-customer-windows.md). `tankapi.ownership.customer_windows`: for one customer and a time range, the stretches in which a device was on that customer's tanks, with the same answer as `owner_at` for every second; a move between its own tanks keeps one stretch; any overlap in the assignments is refused. Read-only, no endpoint, no migration; split from the readings scoping (S-078) for size |
| S-078 | Limit readings to the caller's customer | 3 | **Done** (S-078) | Spec: [`S-078-backend-customer-scoping.md`](S-078-backend-customer-scoping.md). The readings endpoint shows an operator, maintenance or admin caller only scans taken while the device was on their customer's tanks, no untimed scans and only gaps wholly in their time; any other device or time is the unknown device's 404; overlapping assignments a fixed 500; service sees everything. P1-20's isolation tests. Service access not audited yet, so local only; no migration |
| S-079 | Add the append-only audit table | 1 | **Done** (S-079) | Spec: [`S-079-backend-audit-table.md`](S-079-backend-audit-table.md). Table `audit_entries` (migration 0004) for ADR-0008's audit trail: when, `sub`, role, method, route template, device ID, the selecting query parameters and the status; no column for a token, a header or a reading. Triggers refuse UPDATE and DELETE (SQLite tested; the Postgres form, which also refuses TRUNCATE, untested). Nothing writes it yet (S-080); split from S-080 for size |
| S-080 | Audit service-staff access in the backend | 2 | **Done** (S-080) | Spec: [`S-080-backend-service-audit.md`](S-080-backend-service-audit.md). Every `/v1` request by a service caller, refused ones included, writes one row to S-079's `audit_entries`: when, `sub`, role, method, route template, device ID, the `signal`, `from` and `to` parameters as sent and the status; never the token, a header or a reading. A failed write gives 503; customers are not recorded. The daily S3 Object Lock copy is the next audit story; still local only |
| S-081 | Refresh AGENTS.md to the state after S-080 | 1 | **Done** (S-081) | Spec: [`S-081-refresh-agents-md.md`](S-081-refresh-agents-md.md). Section 10 (state, not done, what blocks deployment; the 26 Nov order is complete and no new order is recorded), the backend layout in section 6 and the process lessons since 26 Nov in section 3, plus the stale rows on this page. Documentation only |
| S-082 | Compute level % and volume in the backend | 2 | **Done** (S-082) | Spec: [`S-082-backend-level-volume.md`](S-082-backend-level-volume.md). `tankapi.level.compute_level` turns one radar reading (signal 1001) into level height, level % and volume from a tank's transducer range and strapping table (linear interpolation, never extrapolated), or an explicit `fault`, `out_of_range` or `stale` status with no figures; every result carries the table version and the calculation version. No mass. Table storage, editing with audit, the `interfaces/` schemas and the wiring are later stories; the real pilot table is `[Confirm]` |
| S-083 | Add the stale-reading rule in the backend | 1 | **In review** (S-083) | Spec: [`S-083-backend-stale-rule.md`](S-083-backend-stale-rule.md). `tankapi.liveness` judges a stored reading `live`, `stale` or `time-unknown` against the server clock: a scan with no known time, or ahead of the server, is `time-unknown`; the device's `stale` quality, an `age` over two update periods, or no newer scan within the signal's period plus 14 s (15 s for a one-second signal) is `stale`. Thresholds from environment settings, periods from the signal list; quality never changed. Not in the API yet (S-084); part 1 of P1-19's backend side |
| S-084 | Flag stale readings in the backend | 2 | **In review** (S-084) | Spec: [`S-084-backend-stale-flag.md`](S-084-backend-stale-flag.md). `GET /v1/devices/{device_id}/latest` gives each signal's newest value with quality, age and S-083's `liveness`, plus the device's own state: `time-unknown` when its newest scan has no known time, else live or stale. A stale value comes back flagged, never as live. A customer sees a device only while it is on their tank now, nothing from before the claim; service is audited. Part 2 of P1-19's backend side; the screen is P1-21 and P1-22 |
| S-085 | Store each tank's level configuration in the backend | 2 | **In review** (S-085) | Spec: [`S-085-backend-level-config.md`](S-085-backend-level-config.md). Tables `level_configurations` and `strapping_points` (migration 0005) hold each tank's transducer range, full height and strapping table with the calculation version it is used with, dated from and to so a reading uses the configuration in force at its scan time. The database refuses points that do not rise in both height and volume, gaps, NaN and a second open configuration. Part 1 of the wiring of S-082; reading it at a scan's time and serving the figures is S-086 |
| S-086 | Serve level % and volume from stored radar readings | 2 | **In review** (S-086) | Spec: [`S-086-backend-level-latest.md`](S-086-backend-level-latest.md). `GET /v1/devices/{device_id}/latest` gains `level`: level % and volume computed on read from the newest radar reading, with the configuration of the tank the device was on at its time (`level_config_at`), plus the reading's quality, age and liveness and the table and calculation versions. Figures only when `ok`; otherwise `no_reading`, `unconfigured`, `stale`, `time_unknown`, `fault` or `out_of_range`. Scoping and audit as S-084. Part 2 of 2; the admin write path and the screen are later |
| S-087 | Store each tank's alarm thresholds in the backend | 1 | **Done** (S-087) | Spec: [`S-087-backend-alarm-thresholds.md`](S-087-backend-alarm-thresholds.md). Table `alarm_thresholds` (migration 0006): one high or low limit of class critical, warning or advisory, with a deadband, on one of a tank's eight analogue signals (in its transmitted unit) or on level % (in hundredths of a percent), dated from and to so a change keeps the old limit. The database refuses a device contact or health signal, a level % limit outside 0 to 100 %, a negative deadband and a second open threshold of the same kind. Advisory only; nothing reads it yet. Part 1 of P1-18's backend side |
| S-088 | Judge a value against an alarm threshold in the backend | 2 | **In review** (S-088) | Spec: [`S-088-backend-alarm-rules.md`](S-088-backend-alarm-rules.md). `tankapi.alarm_rules.evaluate` gives normal, high, low, or `cannot_evaluate` with the reason, for one stored reading or S-086 level and one S-087 threshold; a raised alarm stays raised inside its deadband. A fault, unconfigured, stale, untimed or missing value never raises or clears an alarm; an out-of-range reading is judged as measured. Pure, and no backend module can publish to a device. Part 2 of P1-18's backend side |

Decided 26 Nov 2026 and done as their own stories: removing `gateway/` (S-055), moving the link library to `shared/link-protocol/` (S-056), blocking cppcheck and caching the Zephyr tree (S-057).

## Hardware inventory, confirmed by the EE on 20 Nov 2026

Controller is the **NXP FRDM-MCXN947** as ADR-0002 says; "nucleo" in an earlier reply was a slip.

- **15 of 16 digital channels used**, channel 16 spare. Channels 1 to 2 safety switches (**P1-05**), 3 to 9 equipment status (**P1-27**), 10 to 15 alarms (**P1-09**). Full table in `P1-03-signal-list-v1.md`.
- **AD4111: radar level on channel 1, pressure level on channel 2**, two channels free. Each level source also has its own high and low alarm contacts. Pressure level is a raw reading only — comparing it with radar is a Phase 2 mismatch check. This answers story card question 8.
- **Six 3-wire PT100s only** — 2 upper, 2 middle, 2 bottom, 180 degrees apart. One MAX31865, **separate chip select per channel with common SCK, MOSI and MISO** (matches ADR-0002; "daisy chain" in an earlier reply was loose wording).
- **Not present:** over-temperature trip, emergency stop, fire or gas, ambient temperature, wind, thermal oil, heater sheath or pocket sensors.
- **Decided on delegation 20 Nov 2026:** debounce 200 ms on safety and alarm channels, 5 s on equipment status; safety and alarm contacts **normally closed** (fail-safe), equipment status normally open; accuracy target **±2.0 °C** pending the PT100 class.

- **Decided on delegation:** product temperature design range **0 to 200 °C**, accuracy **±2.0 °C** end-to-end. PT100 class still unconfirmed, so ±2.0 °C is the figure to test against; it tightens to ±1.0 °C if the sensors are Class A, which is worth procuring for margin.

**Four stories are void** (P1-07, P1-08, and P1-11 and P1-13 since 26 Nov 2026), returning 15 points, and **one was added** (P1-27, 3 points, not on the story card). Phase 1 is now **24 stories, 95 points** against the card's original 27 and 107 (the totals under the status table above count every row, including the void and undecided ones).

## Tracked document corrections needed

None open. `AGENTS.md` section 5 was corrected to match the EE's inventory in S-012 (PR #26).

## Backlog-level problems to settle before Sprint 2

1. **Epic E3 (P1-11 to P1-16, 23 points) was written for a separate gateway that ADR-0004 removed.** Settled 26 Nov 2026: P1-11 and P1-13 are void, and `gateway/` is removed (S-055).
2. **The story card predates ADR-0004 to ADR-0009.** It still says "all three developers" review `interfaces/` (superseded by S-010), register map (superseded by the YAML signal list), Modbus, OPC UA and VPN.
3. **Stories the ADRs now require that the card does not contain:** ESP32 communications firmware (ADR-0006; started under P1-12 as S-047 and S-064, the ESP-IDF Wi-Fi, TLS, MQTT and 4G glue still to come), device certificate and CA provisioning plus the QR claim flow (ADR-0005), Terraform or OpenTofu blueprints and the test and live environments (ADR-0009), the early cloud test that gates ADR-0007. The 107-point estimate is therefore low.
4. **Known repo chores not on the card:** removing `gateway/` is done (S-055). Correcting the seven merged ADR status lines is done (S-051). Renaming `gitattributes` to `.gitattributes` is done (CHORE-02, S-025), and `pr-policy` reading labels from the event payload is specced as CHORE-03 (S-024).
5. The sprint plan's point totals no longer hold once 1 to 3 are settled.

The story card is a Claude Doc owned by the project manager, so I have not changed it. These are recommendations for it.
