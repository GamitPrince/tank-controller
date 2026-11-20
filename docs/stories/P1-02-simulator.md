# P1-02: Build a simulator for level, temperature, switch-status and trip-status signals, with fault injection

- Story ID: `[Confirm]` — not yet issued.
- Epic: E1 Foundation. Points: 5. Priority: Must. Component: simulator. Review flag: none.

## Goal
A standalone simulator that produces every Phase 1 signal so firmware, cloud and dashboard work can be developed and tested with no hardware.

## Phase check
Phase 1. Test tooling only. It simulates the safety-chain *status inputs*; it must never simulate an output to the safety chain.

## Decisions already made
- **ADR-0004 decision 13:** standalone **Python** simulator, using the same schema and signal list as the real devices, started from one command, with fault injection and outage replay that keeps original timestamps.
- **ADR-0004 decisions 5, 6, 9:** the "same interfaces as real devices" now means the framed protocol (COBS, sequence numbers, CRC), CBOR records against the CDDL schema in `interfaces/`, and signals identified by numeric ID from the YAML signal list. **Not Modbus.**
- 80% line coverage with a `simulator/ci.sh` writing Cobertura `coverage.xml`.

## Files to create or change
- `simulator/` — Python package, entry point, `ci.sh`, tests.
- Reads `interfaces/` schema and signal list; does not define its own copy.

## Interfaces touched
Consumes `interfaces/` (read-only). Needs one non-author collaborator's review if it changes anything there.

## Acceptance criteria (from the story card)
- Produces every Phase 1 signal over the same interfaces as real devices.
- Can inject a sensor fault, an out-of-range value and a link drop.
- Starts from one command with no hardware.
- Plus: 80% line coverage, outage replay keeps original timestamps (ADR-0004.13).

## Test plan
Self-testing: unit tests on the record encoder, fault injection and the replay clock. Simulator output decoded against the CDDL schema.

## Dependency
**Blocked by P1-03.** The signal list and CDDL schema must exist first, or the simulator will invent its own signal IDs.

## Out of scope
Modbus, OPC UA, any real hardware, any control or actuation.

## Open questions
- `[Confirm]` Does the simulator emulate the FRDM (UART framed protocol) or the ESP32 (MQTT to the cloud), or both? ADR-0004.13 does not say.
- `[Confirm]` Fault-injection interface: config file, CLI flags or an API?
