# P1-06: Read multi-zone PT100 product temperatures

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2. Points: 5. Priority: Must. Component: firmware. Review flag: REG (adds signals to `interfaces/`).
- Status: **Unblocked.** The channel-budget conflict is resolved: six PT100s, six channels.

## Goal
Read the product temperature at all six installed points and report each with a quality flag.

## Phase check
Phase 1. Read-only. **No comparison between the paired sensors** — stratification and sensor-mismatch checks are Phase 2.

## Decisions already made
- **ADR-0002, confirmed by the EE 20 Nov 2026:** six 3-wire PT100s, one **MAX31865**, **separate chip-select pin per channel** with common SCK, MOSI and MISO. No other PT100s are installed.
- **ADR-0003:** own hardware layer; hardware layer counts towards the 80% coverage gate; simulated chips on `native_sim`.

## Sensor layout (EE, 20 Nov 2026)
Two sensors per level, **180 degrees apart** across the tank diameter:

| Level | Positions |
| --- | --- |
| Upper | A (0 degrees), B (180 degrees) |
| Middle | A (0 degrees), B (180 degrees) |
| Bottom | A (0 degrees), B (180 degrees) |

**This replaces the story card's zone list** ("bottom, mid, upper, heater zone, outlet, return"). There is no heater-zone, outlet or return PT100. `AGENTS.md` section 5 still carries the old list and needs correcting by PR.

## Accuracy
**±2.0 °C end-to-end** over the product operating range `[Confirm range]`, assuming Class B sensors. Tightens to ±1.0 °C if Class A is confirmed. Full budget in P1-03.

## Files to create or change
`firmware/src/` hardware layer (MAX31865 driver with six chip selects) and measurement layer (linearisation, quality flags). Layout per ADR-0003's four layers. Signal entries in `interfaces/`.

## Acceptance criteria
- All six installed sensors are read and logged, each identified by level and position.
- A broken or shorted RTD is **flagged within 60 s and excluded** from displayed values, never silently replaced.
- Accuracy meets ±2.0 °C `[Confirm sensor class]`.
- Each value carries a quality flag.
- Unit test coverage at or above 80%.

## Test plan
`native_sim` with a simulated MAX31865 on a fake SPI bus: nominal, open circuit, short, out-of-range, fault register set, one channel failed while five are healthy, chip-select addressing wrong channel. Callendar-Van Dusen linearisation checked against reference values. Bench test with real PT100s recorded with P1-25.

## Dependency
P1-03 (signal list) first.

## Out of scope
Comparing the paired sensors, stratification flags, sensor mismatch (all Phase 2). Heater and thermal-oil temperatures — **they do not exist**, see P1-07. Ambient — does not exist, see P1-08. Any control.

## Open questions
- `[Confirm]` PT100 class and the product operating temperature range.
- `[Confirm]` Signal naming for the six positions.
- `[Confirm]` Reference resistor value and tolerance (0.1% low-tempco 400 Ω recommended).
