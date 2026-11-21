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

| ID | Story | Pts | Status | Note |
| --- | --- | --- | --- | --- |
| P1-00 | Tech stack and ADRs | 5 | **Partly done** | ADR-0003 to 0009 merged. ADR-0002 unwritten (EE), ADR-0001 still Proposed, no layer skeleton builds in CI |
| P1-01 | Repo, protection, PR template, CI skeleton | 3 | **Done** | Residual `ci.sh` work carved out as **CHORE-01** |
| P1-02 | Simulator | 5 | Not started | |
| P1-03 | Signal list v1 | 3 | **Ready to start** | Renamed by ADR-0004. **EE inventory received 20 Nov — no longer blocked** |
| P1-04 | Radar level, volume, mass | 5 | Not started | **Conflict: ADR-0004 moves volume and mass to the cloud** |
| P1-05 | HH and LL switch status | 3 | Ready after P1-03 | EE. Channels 1 and 2, normally closed, 200 ms |
| P1-06 | Multi-zone PT100 | 5 | Ready after P1-03 | Six sensors, 2 upper / 2 middle / 2 bottom at 180 degrees |
| P1-07 | Heater and thermal-oil temps | ~~3~~ | **VOID** | No thermal oil, no spare PT100s. Points returned |
| P1-08 | Ambient and wind | ~~2~~ | **VOID** | No ambient sensor, no wind sensor. Points returned |
| P1-09 | Alarm and trip status | 3 | Ready after P1-03 | EE. **Scope cut: no over-temp, e-stop or fire/gas** |
| P1-10 | Prove no write path to the safety chain | 2 | Not started | EE. **Record cannot live in this public repo** |
| P1-11 | Poll over 4-20 mA, Modbus RTU and TCP | 5 | Not started | **Largely void: ADR-0004 removes the gateway and Modbus** |
| P1-12 | Publish over MQTT | 3 | Not started | Component moves from gateway to firmware and ESP32 |
| P1-13 | OPC UA | 5 | Not started | **No ADR covers OPC UA. Decide Phase 1 or Phase 2** |
| P1-14 | Buffer through an outage | 5 | Not started | Now the FRDM flash log, ADR-0004 decision 12 |
| P1-15 | Clock sync | 2 | Not started | Now SNTP plus boot-relative time, ADR-0004 decision 11 |
| P1-16 | VPN-only remote access | 3 | Not started | **Conflict: ADR-0005 says no VPN in Phase 1** |
| P1-17 | Cloud ingest and retention | 5 | Not started | **Blocked by the three gates in ADR-0007** |
| P1-18 | Threshold alarms with audit trail | 5 | Not started | |
| P1-19 | Stale-data flag | 3 | Not started | |
| P1-20 | Role-based login | 5 | Not started | |
| P1-21 | Main tank screen | 8 | Not started | Signal conflict **resolved**: heater, pump, valve and motor status all exist. **Owner unknown** |
| P1-22 | Colour code with text | 3 | Not started | |
| P1-23 | Trends, CSV, PDF | 5 | Not started | Should, may slip |
| P1-24 | Docs set and Feature Registry | 3 | **Partly done** | README and CHANGELOG exist; runbook and registry missing |
| P1-25 | Bench FAT and `sys-v0.1.0` | 5 | Not started | Needs hardware |
| P1-26 | Figma screen designs | 3 | Not started | **Owner unknown: who builds the dashboard** |
| P1-27 | Valve, pump, motor and heater status | 3 | Ready after P1-03 | **Not on the story card.** Added 20 Nov 2026 — channels 3 to 9 had no story |

## Repo chores

Not on the story card. Repo infrastructure identified while working through Phase 1.

| ID | Chore | Pts | Status | Note |
| --- | --- | --- | --- | --- |
| CHORE-01 | Component `ci.sh` scripts and minimal skeletons | 5 | **Done** (S-015) | `firmware/` and `simulator/` only. Firmware job runs in about 3 minutes, so the 15-minute timeout stood. cppcheck left advisory and Zephyr-tree caching not added — both need a workflow change, so each is its own story |
| CHORE-02 | Rename `gitattributes` to `.gitattributes` | 2 | **Specced** (S-021), not started | Spec: [`CHORE-02-gitattributes-line-endings.md`](CHORE-02-gitattributes-line-endings.md). A one-file rename: all 122 tracked blobs are already LF, so `--renormalize` produces no commit. 107 of 122 working-tree files are CRLF, the 4 `.sh` scripts among them |

Identified but not yet specced, listed under "Backlog-level problems" below: correcting the merged ADR status lines, and deciding the fate of `gateway/`.

## Hardware inventory, confirmed by the EE on 20 Nov 2026

Controller is the **NXP FRDM-MCXN947** as ADR-0002 says; "nucleo" in an earlier reply was a slip.

- **15 of 16 digital channels used**, channel 16 spare. Channels 1 to 2 safety switches (**P1-05**), 3 to 9 equipment status (**P1-27**), 10 to 15 alarms (**P1-09**). Full table in `P1-03-signal-list-v1.md`.
- **AD4111: radar level on channel 1, pressure level on channel 2**, two channels free. Each level source also has its own high and low alarm contacts. Pressure level is a raw reading only — comparing it with radar is a Phase 2 mismatch check. This answers story card question 8.
- **Six 3-wire PT100s only** — 2 upper, 2 middle, 2 bottom, 180 degrees apart. One MAX31865, **separate chip select per channel with common SCK, MOSI and MISO** (matches ADR-0002; "daisy chain" in an earlier reply was loose wording).
- **Not present:** over-temperature trip, emergency stop, fire or gas, ambient temperature, wind, thermal oil, heater sheath or pocket sensors.
- **Decided on delegation 20 Nov 2026:** debounce 200 ms on safety and alarm channels, 5 s on equipment status; safety and alarm contacts **normally closed** (fail-safe), equipment status normally open; accuracy target **±2.0 °C** pending the PT100 class.

- **Decided on delegation:** product temperature design range **0 to 200 °C**, accuracy **±2.0 °C** end-to-end. PT100 class still unconfirmed, so ±2.0 °C is the figure to test against; it tightens to ±1.0 °C if the sensors are Class A, which is worth procuring for margin.

**Two stories are void** (P1-07, P1-08), returning 5 points, and **one was added** (P1-27, 3 points, not on the story card). Phase 1 is now **26 stories, 105 points** against the card's original 27 and 107.

## Tracked document corrections needed

`AGENTS.md` section 5 is wrong in three places and needs a PR: the PT100 zone list, the trip-status list, and the ambient and wind entry. None matches the EE's inventory. These are tracked files, so they need a story and a pull request — not an edit in place.

## Backlog-level problems to settle before Sprint 2

1. **Epic E3 (P1-11 to P1-16, 23 points) was written for a separate gateway that ADR-0004 removed.** Six of 27 stories need rewriting or dropping, not just re-pointing. The `gateway/` folder is obsolete too.
2. **The story card predates ADR-0004 to ADR-0009.** It still says "all three developers" review `interfaces/` (superseded by S-010), register map (superseded by the YAML signal list), Modbus, OPC UA and VPN.
3. **Stories the ADRs now require that the card does not contain:** ESP32 communications firmware (ADR-0006 says a story is "to be created"), device certificate and CA provisioning plus the QR claim flow (ADR-0005), Terraform or OpenTofu blueprints and the test and live environments (ADR-0009), the early cloud test that gates ADR-0007. The 107-point estimate is therefore low.
4. **Known repo chores not on the card:** correct the seven merged ADR status lines; decide the fate of `gateway/`. Renaming `gitattributes` to `.gitattributes` is now specced as CHORE-02 above.
5. The sprint plan's point totals no longer hold once 1 to 3 are settled.

The story card is a Claude Doc owned by the project manager, so I have not changed it. These are recommendations for it.
