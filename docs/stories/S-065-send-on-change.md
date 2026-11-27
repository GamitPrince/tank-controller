# S-065: Send at once when a contact or a quality changes

- Story ID: S-065 (issue #133).
- Epic: E3 (P1-12, NFR-01). Points: 2. Priority: Must. Component: FRDM firmware. Review flag: one collaborator other than the author. Not a safety path: it reads the scans already built and changes nothing in `firmware/src/safety/`.

## Goal
An alarm or a sensor fault does not wait for the 5 s batch. Steady readings still go out five to a frame.

## Phase check
Phase 1, transmit only. It changes when records are sent, not what they hold.

## Why
- **The 5 s wait:** S-063 made the uplink poll every 5 s when caught up, so each frame carries five one-second records. A contact that changes just after a poll would then wait up to about 5 s on the FRDM, plus transport.
- **The target:** NFR-01 asks for data in the cloud within 5 s, and the signal list's 200 ms debounce leaves about 4.8 s of that budget.
- **The decision:** recommended in S-062 and S-063, and chosen by the tech lead on 26 Nov 2026.

## Implementation
- **The rule.** `tank_scan_prompt_change(prev, s, contact_count)` in `scan_builder.h/.c` is pure. A scan is a prompt change when, against the scan logged before it, any reading's quality or value presence changed, or any contact's value changed. The contacts are the builder's last `contact_count` readings. Analogue values move every scan, so they do not count. Scans that do not line up count as changed.
- **Scan service.** After a scan is logged, it compares that scan with the one logged before. On a prompt change it counts the change and calls the new optional `on_change(change_ctx)` from its inputs. Only logged scans are compared, so a scan the flash failed to store never stands in for one that was.
- **Uplink service.** `tank_uplink_service_kick(svc)` gives the service's wake semaphore, so a waiting poll runs at once. A kick during a poll makes the next poll start straight after it. Kicks collapse into one.
- **Application.** The scan service's `on_change` kicks the uplink service. Without a UART there is nothing to kick, and a kick before the uplink is up is refused harmlessly.

## Interfaces touched
None.

## Acceptance criteria
- Analogue noise is not a prompt change. A contact change, a quality change, a value appearing or disappearing, and scans that do not line up are.
- Steady scans call `on_change` never. A quality change calls it once.
- A kick wakes an uplink waiting out a 10 s idle period, and the records arrive within the slack the other timing tests use. A kick to a service that is not running is refused.
- In the application, with a 10 s idle poll, a quality change reaches the emulated ESP32 within about three scan periods.
- All existing suites pass, and 80% line coverage holds.

## Test plan
`native_sim`: `record_scan_builder`, `record_scan_service`, `communications_uplink_service`, `app_tank_app` (with the emulated ESP32). No bench test: the end-to-end 5 s figure is measured device to cloud once the cloud exists (P1-05's test plan already says so).

## Out of scope
- **Rate limiting.** A reading whose quality flips every second would send every second. That is acceptable in Phase 1, and it is visible in the `changes` counter. A limit can follow if the pilot shows it.
- **The cloud and dashboard side of NFR-01.**

## Open questions [Confirm]
1. **What counts as a prompt change:** every quality change counts, not only the safety and alarm contacts (recommended, taken). A sensor fault matters to the operator as much as an alarm, and a fault should never look live for 5 s.

## PR checklist notes
Title `feat(firmware): send at once when a contact or a quality changes (S-065)`, branch `feature/S-065-send-on-change`, `Closes #133`. No `safety` label.
