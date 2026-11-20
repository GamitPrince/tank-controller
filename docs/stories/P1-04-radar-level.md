# P1-04: Read radar level; compute level %, volume and mass

- Story ID: `[Confirm]` — not yet issued.
- Epic: E2 Field sensing. Points: 5. Priority: Must. Component: firmware. Review flag: REG (adds signals).

## Goal
Read the radar level transmitter and make the level available as an engineering value with a quality flag.

## Phase check
Phase 1. Read-only. No output, no control.

## Decisions already made
- **ADR-0002, confirmed by the EE 20 Nov 2026:** radar level arrives as 4-20 mA on **AD4111 channel 1**, input-only. **Channel 2 carries pressure level**, the secondary level measurement; two channels remain free.
- **Each level source has its own alarm contacts:** radar on digital channels 12 and 13, pressure on channels 10 and 11 (read by P1-09).
- **ADR-0003:** own small AD4111 SPI module; hardware layer counts towards the 80% coverage gate; simulated chips on `native_sim` for laptop testing.
- **ADR-0004 decision 10:** **volume and mass are computed in the cloud, not on the controller. The controller is send-only.**

## CONFLICT — must be settled before this story starts
The story card and section 7 question 3 both put the volume and mass calculation **in firmware**. **ADR-0004 decision 10 puts it in the cloud.** The ADR is newer (2 Nov) and merged, so it wins, which splits this story:

- **Firmware part (this story):** read the 4-20 mA input, scale it to a level value, flag sensor failure and out-of-range, send it.
- **Cloud part (new story, does not exist):** level %, volume and mass from the geometry table with temperature-corrected density, plus the stored calculation version (ADR-0007).

The 0.5% accuracy criterion and the density correction therefore belong to the cloud story, not here. **Do not implement either side until the tech lead confirms the split.**

## Files to create or change
`firmware/src/` hardware layer (AD4111 module) and measurement layer. Exact layout per ADR-0003's four layers; the firmware skeleton story decides it. `interfaces/` signal entries.

## Acceptance criteria (story card, with the conflict unresolved)
- Level %, volume and mass match the geometry table within 0.5%. **Cloud, pending the split.**
- Density corrected for temperature. **Cloud, pending the split.**
- A failed radar shows a fault state, **never a stale value**. Firmware.
- Unit test coverage at or above 80%. Firmware.

## Test plan
`native_sim` with a simulated AD4111 returning scripted register values: nominal, below 4 mA, above 20 mA, open circuit. Bench test on the real board recorded later with P1-25.

## Dependency
P1-03 (signal list) first.

## Pressure level — story card question 8, answered
The secondary pressure level **is** measured, on AD4111 channel 2. Per the card's own assumption it is read and shown as a **raw value only**: comparing it against radar level is a sensor-mismatch check and that is **Phase 2**. Do not average, cross-check or substitute one for the other.

`[Confirm]` whether reading pressure level belongs in this story alongside radar — it is the same AD4111 driver, so splitting it into its own story would duplicate the work.

## Out of scope
Any write to the AD4111 beyond configuration. Comparing radar against pressure level (Phase 2).

## Open questions
- `[Confirm]` Split firmware and cloud as above?
- `[Confirm]` Where does the geometry table live, and who owns it?
- `[Confirm]` Does this story also read pressure level, or does that get its own story?
