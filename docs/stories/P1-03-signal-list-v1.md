# P1-03: Define the Phase 1 signal list v1 (replaces "register map v1")

- Story ID: `[Confirm]` — not yet issued. Next free is S-012.
- Epic: E1 Foundation. Points: 3. Priority: Must. Component: interfaces.
- Review flag: story card says ALL3. **Superseded by S-010:** one approval from a collaborator other than the author.
- Status: **Unblocked.** The EE supplied the full signal inventory on 20 Nov 2026.

## Goal
One versioned, machine-readable definition of every Phase 1 signal, so firmware, simulator, cloud and dashboard all mean the same thing by the same name.

## Phase check
Phase 1 signals only. No Phase 2 signals (vibration, noise, exhaust, fuel, power). No comparison or mismatch logic between signals — that is Phase 2.

## Decisions already made
- **ADR-0004 decision 9:** a versioned **YAML signal list with numeric IDs** in `interfaces/` **replaces the register map**. Each signal: numeric ID, name, unit, scale, update rate, read-only flag. Records identify signals by ID and carry one timestamp per scan.
- **ADR-0004 decision 6:** CBOR records with a **CDDL schema**, also in `interfaces/`.
- **ADR-0002:** 16-channel optocoupler digital inputs (status-only); 6-channel MAX31865 for 3-wire PT100 on a shared SPI bus with **six separate chip selects** and common SCK, MOSI and MISO; AD4111 4-20 mA with two of four channels used.

## Signal inventory (EE, 20 Nov 2026)

### Digital inputs — 15 used of 16 channels
All at the pilot site. Channel 16 is spare.

| Ch | Signal | Class | Contact sense | Debounce |
| --- | --- | --- | --- | --- |
| 1 | High-high level switch | Safety-chain read | Normally closed | 200 ms |
| 2 | Low-low level switch | Safety-chain read | Normally closed | 200 ms |
| 3 | Inlet valve status | Equipment status | Normally open | 5 s |
| 4 | Inlet pump status | Equipment status | Normally open | 5 s |
| 5 | Outlet pump status | Equipment status | Normally open | 5 s |
| 6 | Outlet valve status | Equipment status | Normally open | 5 s |
| 7 | Mixture motor on/off | Equipment status | Normally open | 5 s |
| 8 | Base heater on/off | Equipment status | Normally open | 5 s |
| 9 | Main heater on/off | Equipment status | Normally open | 5 s |
| 10 | Low pressure level alarm | Alarm | Normally closed | 200 ms |
| 11 | High pressure level alarm | Alarm | Normally closed | 200 ms |
| 12 | Low radar level alarm | Alarm | Normally closed | 200 ms |
| 13 | High radar level alarm | Alarm | Normally closed | 200 ms |
| 14 | Low mixture temperature alarm | Alarm | Normally closed | 200 ms |
| 15 | Dry run alarm | Alarm | Normally closed | 200 ms |
| 16 | *(spare)* | — | — | — |

**Contact sense rationale (decided 20 Nov 2026):** the eight safety and alarm channels are **normally closed**, so a de-energised device or a broken wire reads as *alarm*, not as healthy. This is fail-safe for monitoring integrity and satisfies `AGENTS.md` section 7 ("never show stale data as live", "failed sensors are flagged"). The seven equipment-status channels are **normally open**, where open simply means not running.

**Debounce rationale:** 200 ms on safety and alarm channels leaves about 4.8 s of the NFR-01 five-second budget for scan, transmit, ingest and render. 5 s on equipment status suppresses contactor chatter where latency does not matter.

### PT100 temperatures — 6 of 6 MAX31865 channels
Six 3-wire PT100s only; no others are installed. Two per level, mounted at **180 degrees apart** across the tank diameter.

| Ch | Signal `[Confirm names]` | Level | Position |
| --- | --- | --- | --- |
| 1 | Product temperature, upper A | Upper | 0 degrees |
| 2 | Product temperature, upper B | Upper | 180 degrees |
| 3 | Product temperature, middle A | Middle | 0 degrees |
| 4 | Product temperature, middle B | Middle | 180 degrees |
| 5 | Product temperature, bottom A | Bottom | 0 degrees |
| 6 | Product temperature, bottom B | Bottom | 180 degrees |

**No heater-zone, outlet, return, heater sheath, heater pocket, thermal-oil or ambient PT100 exists.** The pair at each level is read and reported independently; comparing them is Phase 2.

### Analogue 4-20 mA — AD4111
| Signal | Note |
| --- | --- |
| Radar level | The primary level measurement (P1-04) |
| *(second channel)* | `[Confirm]` what occupies the second of the two used channels — pressure level? |

### Not present in Phase 1
Over-temperature trip and emergency stop exist at the site but are **not routed to this board**. No fire or gas. No ambient temperature. No wind sensor.

## Accuracy target (decided 20 Nov 2026, pending the sensor class)
**NFR-02: ±2.0 °C end-to-end** over the product operating range `[Confirm range; 0 to 200 °C assumed]`.

Budget: PT100 Class B tolerance is ±(0.3 + 0.005·t), about ±1.2 °C at 180 °C; MAX31865 plus reference resistor about ±0.5 °C; 3-wire lead imbalance residual about ±0.2 °C. The PT100 class has not been confirmed, so the pessimistic Class B figure is used.

**Recommendations:** procure Class A sensors, which would allow tightening to **±1.0 °C**; specify a **0.1% low-temperature-coefficient 400 Ω reference resistor** for the MAX31865.

## Files to create or change
- `interfaces/signals-v1.yaml` `[Confirm name]` — the 22 signals above plus device health.
- `interfaces/records.cddl` `[Confirm name]` — CBOR record schema.
- `interfaces/README.md` — the version rule.

## Interfaces touched
This story *is* the interface. Needs one non-author collaborator's approval, and `interfaces-review` must be green.

## Acceptance criteria
- Every Phase 1 signal has a numeric ID, name, unit, scale, update rate and read-only flag.
- Contact sense and debounce are recorded per digital channel.
- The list carries a version number.
- The CDDL schema validates a record produced by the simulator.
- Approved by a collaborator other than the author.

## Conflicts with other documents
- **"Register map" is obsolete** (ADR-0004.9). The story card title, RSD FR-COM-01 and the `REG` flag on P1-04 to P1-08 need rewording.
- **`AGENTS.md` section 5 is wrong in two places** and needs a PR: the PT100 zone list ("bottom, mid, upper, heater zone, outlet, return") and the trip list ("over-temp, e-stop, pump dry-run, fire/gas"). Neither matches the EE's inventory.

## Dependency
Blocks P1-02 and every story that reads a signal. **Start here.**

## Out of scope
Modbus addresses, OPC UA node IDs, MQTT topic layout (undecided, `AGENTS.md` section 6). Any comparison between the paired PT100s.

## Open questions
- `[Confirm]` Signal names and the numbering scheme for the six PT100 positions.
- `[Confirm]` What occupies the second used AD4111 channel.
- `[Confirm]` PT100 class and the product operating temperature range.
- `[Confirm]` File names and whether the version is in the filename or a `version:` field.
- `[Confirm]` Does the signal list also cover cloud-computed values (level %, volume, mass), or only what the device sends?
