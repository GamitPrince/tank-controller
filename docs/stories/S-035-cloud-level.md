# S-035: Cloud level %, volume and mass calculation

- Story ID: S-035 (issue #74).
- Epic: cloud (not on the original Phase 1 Story Cards; split from P1-04, same as P1-27 was split from the digital channel inventory). Points: `[Confirm]`. Priority: Must. Component: backend. Review flag: one non-author collaborator (not a safety path; no EE approval needed).
- **This story is the cloud half of P1-04.** P1-04 (S-034, PR #73, merged) now reads and sends the radar (signal 1001) and pressure (signal 1002) loop currents in mA, with a quality flag, and does nothing else. Everything below was carved out of P1-04's acceptance criteria by the tech lead's resolution of 2026-11-23, recorded in `docs/stories/P1-04-radar-level.md`.

## Goal
Compute level %, volume and mass in the cloud backend from the radar level reading, the tank geometry table and temperature-corrected density, and store the calculation version alongside every result.

## Phase check
Phase 1. Read-only with respect to the plant: this story only computes and stores values from data the device already sends. It adds no command path (ADR-0004 decision 10: the controller is send-only; ADR-0008 decision 9: the dashboard is read-only for plant data). No AI or analytics — this is a deterministic geometry/physics calculation, not Phase 3 predictive work.

## Decisions already made
- **ADR-0004 decision 10:** volume and mass are calculated in the cloud backend from the tank geometry table and a temperature-corrected density, not in firmware. The firmware sends level and temperatures with quality flags only.
- **ADR-0007 decision 4:** the readings and records database is Tiger Cloud (managed TimescaleDB / PostgreSQL) on AWS, including tank geometry tables.
- **ADR-0007 decision 9 (proposed rule, confirmed with this ADR):** volume and mass are calculated from the geometry table and a temperature-corrected density, with the calculation version stored beside each result so figures can be reproduced from the raw archive.
- **ADR-0008 decision 1:** backend is Python (FastAPI).
- **ADR-0008 decision 3:** tank settings (which includes the geometry table) are an admin-role permission; changes go through the backend, which checks role and customer/plant scope on every request.
- **ADR-0008 decision 4:** tank settings changes are written to the append-only audit trail (who, what, when, value before and after), also copied daily to S3 with Object Lock.
- **P1-04 resolution, 2026-11-23:** the tank geometry table lives in the cloud and the tech lead owns it. This story reads radar level (signal 1001) only for the level/volume/mass calculation; pressure level (signal 1002) is a raw secondary value, not an input to this calculation (see "Pressure level" below).
- **Tech lead, 2026-11-23 (this story):** the pilot tank is a vertical tank with a spherical bottom head, not a plain cylinder. The geometry table is therefore a strapping-table model (level height → volume), not a closed-form cylinder formula, so it can represent the spherical bottom and any other shape a later tank needs without a schema change.
- **Tech lead, 2026-11-23 (this story):** no product density-vs-temperature reference data exists yet. This story defines the schema and the lookup/calculation method only; populating real density data for a specific product is explicitly out of scope (see "Out of scope").
- **Tech lead, 2026-11-23 (this story):** backend code lives in a new top-level `backend/` component (not under `dashboard/`), alongside `firmware/`, `dashboard/`, `simulator/`. It needs its own `backend/ci.sh` (pytest + coverage, per ADR-0008 decision 6) to pass the 80% coverage gate — adding that skeleton is in scope here since without it this story's code cannot pass CI.

## Files to create or change
- `backend/` — new component. Minimum for this story: the geometry/volume/mass calculation module, its unit tests, and `backend/ci.sh` (builds, lints, runs pytest with coverage, writes `coverage.xml`). No API endpoints, no database connection code, no deployment — this story is the calculation itself, callable with plain Python inputs (current + temperatures + a geometry table object) and testable without any cloud account.
- `interfaces/` — no new device signal (this story consumes existing signals 1001, 2001-2006; it does not add to `interfaces/signals-v1.yaml`). **Resolved by the tech lead, 2026-11-23:** the geometry-table and computed-value record schemas are kept in `interfaces/` (CDDL or similar, matching ADR-0004 decision 6's pattern), not backend-internal, so they get the same one-non-author-approval review as the signal list.
- `docs/adr/` — none. This story implements decisions already in ADR-0004, 0007, 0008; it does not make new architecture decisions.

## Interfaces touched
None in `interfaces/signals-v1.yaml` (no new device signal). The geometry-table and computed-record schemas belong under `interfaces/` (resolved above), so the PR that adds them needs one non-author collaborator's approval and `interfaces-review` green, same as any other `interfaces/` change.

## Calculation

### 1. Level %
Level % is derived from the radar loop current (signal 1001, `level_radar_loop_current`, mA) and the transducer's calibrated current-to-level span.

- `[Confirm]` **Transducer range.** No 4-20 mA span (for example, 0-6000 mm) has been supplied for the radar transmitter. Until it is, level % cannot be computed from the current; record the range as a geometry-table field (see below) populated later, and until it is populated, treat level % (and therefore volume and mass) as not computable and report "no computed value" per the quality rule below, not a placeholder.
- Loop current is first checked against the firmware's own fault flagging: a reading already flagged `fault` (below 3.6 mA / above 21 mA, `[Confirm]` in P1-04) and any input `quality` flag other than good from the record envelope are both treated as "no computed value" (see Quality handling).

### 2. Volume: strapping-table geometry model
The geometry table maps level height to volume directly (a strapping table), rather than a closed-form formula, so it can represent the pilot tank's vertical cylinder with a spherical bottom head, and any future tank shape, without a schema change.

Proposed schema (table per tank, owned by the tech lead, stored in the cloud database per ADR-0007 decision 4):

| Field | Type | Notes |
| --- | --- | --- |
| `tank_id` | reference | which tank this table belongs to |
| `version` | integer, monotonically increasing | bumped on every edit; see "Versioning and audit" |
| `effective_from` | timestamp | when this version takes effect for new calculations |
| `transducer_range_low_mm` / `transducer_range_high_mm` | numeric | per-tank configuration, not a system constant (resolved 2026-11-23 — see "Resolved by the tech lead" below); `[Confirm]` per site, populated at commissioning |
| `points[]` | list of `(height_mm, volume_l)` | strapping-table rows, monotonically increasing in both fields; interpolation is linear between points; **denser points are mandatory through the heater-affected bottom zone** (resolved 2026-11-23) |
| `heater_zone_top_mm` | numeric | height up to which the base heater displaces volume; the table must carry noticeably closer points below this height than above it |
| `max_height_mm` | numeric | tank full height, for out-of-range detection |

Volume at a given level height is linear interpolation between the two bracketing `points` rows. A height below the lowest point or above `max_height_mm` is out-of-range (see Quality handling), not extrapolated.

**Resolved by the tech lead, 2026-11-23:** the strapping table is always supplied as a finished list of points, never generated by this backend from parametric dimensions. The pilot tank has a base heater fitted at the bottom that displaces volume, so below `heater_zone_top_mm` the volume-to-height relationship is not even the spherical-head formula, let alone a cylinder — it depends on the heater's physical shape and position, which only a supplied table (from the tech lead or a tank-geometry vendor calculation) can capture. Above the heater zone, height and volume are consistent (a plain cylinder), so the table can use wider point spacing there. A parametric generator is therefore not viable for this tank shape and is dropped, not deferred.

### 3. Mass: temperature-corrected density
Mass = volume × density, where density is looked up from a density-vs-temperature reference table for the tank's configured product, at a single representative product temperature derived from the six PT100 readings (signals 2001-2006).

- **No density reference data exists yet.** This story defines the schema (`product_id`, and a `(temperature_degC, density_kg_per_l)` table, with linear interpolation between points and out-of-range outside the table's ends) and the lookup method only. Populating real density data for an actual product is tracked separately as **S-037** (issue #77), a dependency of this calculation going live.
- **Temperature source and pair handling, resolved by the tech lead, 2026-11-23** (pair-average, then mean of levels):
  - The two sensors in each pair (upper-a/upper-b, middle-a/middle-b, bottom-a/bottom-b) are mounted 180 degrees apart at the same height to read the same point from two sides. Averaging a pair is a **redundancy combination**, not the Phase 2 cross-check (which would compare readings *across* levels or instruments to detect a mismatch — out of scope here, same as P1-04's radar/pressure rule). Each pair is therefore averaged arithmetically, provided both sensors in the pair are good quality; if one sensor in a pair is faulted, the other alone stands in for that level (still not a cross-check, since there is nothing left to compare); if both are faulted, that level has no representative temperature (see Quality handling).
  - The three per-level temperatures (upper, middle, bottom) are combined into one representative product temperature using a simple arithmetic mean of whichever levels have a valid reading. This spec does **not** weight by how much of the tank is submerged at each level (that would use the just-computed level, which is itself provisional on the per-tank transducer range, and adds a second quality dependency); a depth-weighted mean was considered and rejected for this story, since the 0.5% criterion is a volume accuracy target, not a density accuracy target.
  - If every one of the six readings is faulted, mass is not computable (Quality handling).

### 4. Accuracy criterion (moved from P1-04)
Level %, volume and mass must match the geometry table within 0.5%, for a given level height, transducer range and geometry table version. This is a geometry/interpolation accuracy target (does the calculation reproduce the table correctly), not a sensor accuracy target — sensor accuracy is bounded separately by the transducer's own spec and the PT100 accuracy budget (±2.0 °C, ADR-0003/signal list).

### 5. Calculation version (ADR-0007 decision 9)
Every computed level %/volume/mass result stores, alongside the figures: the geometry table `version` used, the density reference table version used (once one exists), and a calculation-code version (for example a semantic version or git commit hash of the `backend/` calculation module). This lets any stored figure be reproduced later from the raw archive even after the geometry or density tables change.

## Quality handling
- A fault or stale input (radar current flagged `fault`, record `quality` not good, or a PT100 reading flagged faulted/stale per P1-06) means **no computed value** for whichever output it affects — never a silent substitute, interpolation across the gap, or a last-known-good figure presented as current. This applies independently to volume (depends only on radar level) and mass (depends on volume and temperature): a temperature fault can still let level % and volume be reported while mass is withheld.
- A level height or computed value outside the geometry table's range (below the lowest strapping point, above `max_height_mm`) is reported as **out-of-range**, a distinct state from "no computed value due to a fault" — both must be distinguishable to a consumer (dashboard or API caller), not collapsed into one generic "unavailable" flag.
- "No computed value" is a real, representable state in the stored record, never a null that could also mean "not yet calculated." **Resolved by the tech lead, 2026-11-23:** the record carries an explicit `status` enum — `ok`, `fault`, `out_of_range`, `stale` — rather than overloading a null or a sentinel numeric value.

## Pressure level
Pressure level (signal 1002) is stored and made available as a **raw secondary value only** (already true as sent by firmware, unscaled by any geometry). This story does not use it as an input to level %, volume or mass, and does not compare it against the radar-derived level — that comparison is a Phase 2 sensor-mismatch check (per P1-04 and the story card's resolved question 8).

## Geometry table: storage, ownership, versioning and audit
- **Storage:** the cloud database (Tiger Cloud / PostgreSQL), per ADR-0007 decision 4, which already names tank geometry tables as one of the record types it holds.
- **Schema:** as in "Volume: strapping-table geometry model" above — versioned, with `points[]` as the strapping table.
- **Ownership:** the tech lead edits the geometry table (admin role, ADR-0008 decision 3: "admin manages that customer's users and tank settings such as the geometry table"). No technician-specific permission exists (ADR-0008: technicians use named admin accounts, not a separate role).
- **Versioning:** every edit creates a new `version` row rather than overwriting the previous one (append, don't mutate), with `effective_from` controlling when it applies to new calculations. Past calculations keep referencing the `version` they were computed with (see Calculation version above), so a geometry correction never silently changes a historical figure.
- **Audit:** every geometry table change is written to the append-only audit trail (who, what, when, before/after), per ADR-0008 decision 4, and included in the daily S3 Object Lock copy. This is the same mechanism as other "tank settings changes," not a separate audit path for geometry specifically.

## Backend component
Backend code lives in a new top-level `backend/` folder (tech lead, 2026-11-23), alongside `firmware/`, `dashboard/`, `simulator/`, `hardware/`, `interfaces/`. This story adds only the calculation module, its tests and `backend/ci.sh`; it does not add API endpoints, a database connection, a container build, or any deployment — those belong to later backend stories (API, ingest, auth) that ADR-0007/0008 still list as "to be created."

## Test plan
All tests run against the calculation module directly (Python, pytest), with no cloud account and no real database — `[Confirm]` whether a geometry table and density table are represented as in-memory fixtures/dataclasses for this story's tests, or as a local file format; either way, no AWS resource is touched.

Cases:
- A nominal radar current in range, a geometry table with a few strapping points spanning a spherical-bottom-like curve, all six PT100s good: level %, volume and mass computed, calculation version recorded, matching a hand-calculated expected value within 0.5%.
- Radar current flagged `fault`: no computed value for level %, volume or mass; state is distinguishable from out-of-range.
- Radar current in range but corresponding level height outside the geometry table's `points` span (or above `max_height_mm`): out-of-range, not extrapolated.
- One PT100 in a pair faulted, its partner good: that level's temperature comes from the surviving sensor alone; mass still computed.
- Both PT100s in one pair faulted, the other two pairs good: representative temperature from the two good levels; mass still computed.
- All six PT100s faulted: level % and volume still computed (radar-only), mass withheld as "no computed value."
- A new geometry table version is added effective from a future time: a calculation run before that time still uses the old version; the calculation version recorded matches whichever table version was actually used.
- Pressure level (signal 1002) is present in the input but never enters the level/volume/mass calculation; a test asserts this explicitly (for example, varying the pressure-level input leaves the computed values unchanged).
- The simulator (ADR-0004 decision 13, `simulator/`) is the source of the radar current, temperatures and quality flags used to assemble these test inputs. **Resolved by the tech lead, 2026-11-23:** wiring the simulator to the backend end-to-end over MQTT is a follow-up ingest story, not part of S-035 — this story's tests call the calculation module directly with fixture inputs. End-to-end wiring waits on P1-17 (cloud ingest), which ADR-0007's three gates still block.

## Out of scope
- No dashboard screens (P1-21, P1-22, P1-23 — owner still unassigned per AGENTS.md section 6).
- No command of any kind to any device — this story, like the whole cloud side in Phase 1, is receive/compute/store only.
- No cloud account opened, no paid service added, no AWS resource created or configured — ADR-0007's three gates (customers' answers, the early cloud test, a Tiger Cloud quote) have not passed. This story's code runs and is tested entirely locally/in CI.
- Populating real product density-vs-temperature data — schema only, as noted above; tracked as S-037 (issue #77).
- The depth-weighted temperature refinement mentioned under "Mass" — considered and rejected for this story, not deferred.
- API endpoints, authentication, ingestion from the message queue, and anything else ADR-0007/0008 still list as "to be created" for the backend.
- Comparing pressure level against radar level (Phase 2 sensor-mismatch check).

## Dependency
P1-04 (S-034, merged) for the signals this story consumes (1001, 1002, 2001-2006). No dependency on P1-17 (cloud ingest) — this story's calculation is testable standalone, as the test plan above describes.

## Resolved by the tech lead, 2026-11-23 (S-036)
- Strapping table is always supplied as finished points; never generated here from parametric dimensions, because the base heater at the bottom displaces volume in a way no formula captures.
- The table must carry denser points through the heater-affected bottom zone (below `heater_zone_top_mm`) than above it.
- Temperature combination: average each 180-degree PT100 pair, then arithmetic mean of whichever levels are valid.
- The geometry-table and computed-record schemas belong in `interfaces/`, reviewed like the signal list.
- End-to-end wiring to the simulator over MQTT is a follow-up ingest story, not part of S-035.
- "No computed value" / out-of-range is an explicit `status` enum (`ok`, `fault`, `out_of_range`, `stale`) in the stored record.
- The radar transducer's current-to-level range is per-tank configuration (already a field on the geometry table row, not a system constant); for the pilot it comes from that tank's own known dimensions as a test fixture, with the real figure supplied at each site's commissioning.
- Populating real product density data is tracked as its own story, S-037 (issue #77), not folded into S-035.

## Open questions
- `[Confirm]` Story points — not estimated here.
- `[Confirm]` Exact point spacing required through the heater-affected bottom zone to hit the 0.5% target — a number, not just "denser," still needs a value once a real tank's heater geometry is known.
