# S-082: Compute level % and volume in the backend

- Story ID: S-082 (issue #167).
- Epic: cloud, the cloud half of P1-04. Points: 2. Priority: Must. Component: backend (`backend/`). Review flag: one collaborator other than the author. Not a safety path; `.github/`, `interfaces/` and the migrations are not touched; no new dependency. Chosen by the tech lead on 27 Nov 2026. Built from the S-035 spec (issue #74, closed), with its mass sections dropped.

## Goal
Turn one radar level reading (signal 1001) into a level height, a level % and a volume, using a tank's transducer range and strapping table, and say plainly when no figure can be given. This is the calculation the main tank screen (P1-21) will later show.

## Phase check
Phase 1, read-only for plant data. A pure calculation on values the device already sends: nothing is sent to a device, nothing is stored, no endpoint changes. No AI or analytics (a deterministic table lookup). No AWS resource or account (ADR-0007's three gates still hold). No mass: density-based mass left Phase 1 on 26 Nov 2026 (S-053, S-037 closed).

## Decisions already made
- **ADR-0004 decision 10 and amendment 1:** level % and volume are computed in the backend from the tank geometry table, not in the firmware; no density table and no mass in Phase 1.
- **ADR-0007 decision 9 and amendment 4:** the calculation version is stored beside each result so figures can be reproduced from the raw archive.
- **ADR-0008 decision 3:** tank settings, the geometry table among them, are the admin role's. Nothing here edits them.
- **S-035, resolved by the tech lead on 23 Nov 2026:** the geometry is a strapping table of finished `(height_mm, volume_l)` points, linear interpolation between them, never extrapolated and never generated from dimensions (the pilot tank has a dished bottom and internal heating coils); the transducer range is per-tank configuration on the table; the result has an explicit status `ok`, `fault`, `out_of_range` or `stale`; tables are in-memory Python objects in this story's tests; pressure level (signal 1002) is not an input.
- **signals-v1.yaml, signal 1001:** the loop current is sent in microamps (`scale: 0.001`), valid from 4.0 to 20.0 mA. The firmware (S-034) flags below 3.6 mA or above 21 mA as `fault` with no value, and 3.6 to 4.0 or 20 to 21 mA as `out-of-range`.

## Files to create or change
- `backend/tankapi/level.py` (new): `StrappingTable`, `StrappingPoint`, `LevelResult`, `LevelStatus`, `compute_level`, `CALCULATION_VERSION`.
- `backend/tests/test_level.py` (new), with a made-up test table labelled as such.
- `backend/README.md`, `docs/stories/README.md`, `CHANGELOG.md`.

## Interfaces touched
None. `interfaces/` and the OpenAPI document are unchanged. The strapping-table and computed-record schemas that S-035 places in `interfaces/` are a later story.

## Acceptance criteria
- A good reading in range gives `ok` with the level height (the transducer range scaled linearly over 4 to 20 mA), level % of `max_height_mm` (the height, resolved 27 Nov 2026) and the interpolated volume, each reproducing hand-calculated values and every strapping point exactly (well inside S-035's 0.5%).
- Reading quality `stale` gives `stale`; `out-of-range` gives `out_of_range`; `fault` and `unconfigured` give `fault` (resolved 27 Nov 2026). A `good` reading outside 4 000 to 20 000 µA gives `out_of_range`, and a true/false value gives `fault`.
- A level below the lowest strapping point or above the highest gives `out_of_range`, not an extrapolation.
- Every result, `ok` or not, carries the table's `version` and `CALCULATION_VERSION`; only `ok` carries figures, every other status has none.
- A table whose numbers are not finite, whose version is below 1, whose transducer range does not rise from 0 mm or more, which has fewer than two points, whose first point is negative, whose points do not rise in both height and volume, or whose points end above `max_height_mm`, is refused when it is made.
- Signal 1002 (pressure level) is refused as an input.

## Test plan
pytest, locally on Windows against the new test file and in GitHub CI (`backend` job, 80% line-coverage gate). Cases: hand-calculated figures in the slow-rising bottom zone and higher up; every strapping point reproduced; 100% at full height; a raised transducer low end; above full height, past the tank and below the lowest point; every non-good quality and the defensive checks; pressure refused; each broken-table case. No bench test: nothing touches hardware. No real tank data: the test table is made up.

## Out of scope
Split into later stories to stay under about 300 changed lines: the strapping-table storage (versioned rows with `effective_from`, a migration), choosing the version in effect at a scan's time, storing computed results, the admin endpoint to edit a table with its audit entry (ADR-0008 decisions 3 and 4), the `interfaces/` schemas for the table and the computed record, and wiring the calculation into ingest or the readings endpoint. Also out: the real pilot table, any mass or density, comparing pressure with radar (Phase 2), any AWS resource, and any dashboard screen.

## Resolved by the tech lead, 27 Nov 2026
- Level % is the level height as a share of the tank's full height (`max_height_mm`), not the volume as a share of the full volume.
- The quality mapping was left to the author and is kept as built: a reading the firmware flags `out-of-range` (3.6 to 4.0 or 20 to 21 mA) gives `out_of_range`, because the transmitter works but the level is past its span; `unconfigured` gives `fault`, because S-035's enum has no unconfigured state. Neither carries a figure.
- No minimum point count beyond the two that interpolation needs (S-035 open question 3): S-035's 0.5% accuracy criterion, checked against the tank's own calibration chart, is what proves a table fine enough.
- `CALCULATION_VERSION` is a whole number raised by hand whenever the method changes, not a git commit hash.

## Open questions
1. `[Confirm]` The pilot tank's real strapping table, transducer range and full height, from the tech lead at commissioning. Customer data: entered into the cloud table, never committed here.
2. `[Confirm]` NAMUR NE43 limits 3.6 and 21 mA, against the radar transmitter's datasheet or settings (S-034's open item, only referenced here).
