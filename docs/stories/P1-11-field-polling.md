# P1-11: Poll field devices over 4-20 mA, Modbus RTU and Modbus TCP

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3 Gateway and telemetry. Points: 5. Priority: Must. Component: gateway (card). Review flag: none.
- Status: **Largely void. Do not start. Needs a backlog decision first.**

## MAJOR CONFLICT — this story was written for an architecture that no longer exists
The story card (26 Oct) assumed a separate gateway polling field devices over Modbus. Three merged ADRs removed that:

| Card assumption | Current decision |
| --- | --- |
| A separate gateway polls the controller | **ADR-0004 decision 1:** no separate gateway. The FRDM-MCXN947 collects and communicates itself |
| Modbus RTU and Modbus TCP | **ADR-0002:** RS-485 is not needed in Phase 1. **ADR-0004 decision 9:** the YAML signal list replaces the register map. No ADR mentions Modbus anywhere |
| 4-20 mA polled by the gateway | **ADR-0002 and ADR-0003:** 4-20 mA is read directly by the FRDM through the AD4111 over SPI — that is P1-04 |

What survives of the intent is already covered: analogue reads in P1-04 and P1-06 to P1-08, digital status in P1-05 and P1-09, the FRDM-to-ESP32 link in a new ESP32 story that does not yet exist.

## Recommendation (tech lead decides, not this spec)
Drop P1-11, reassign its 5 points, and create instead the **ESP32 communications firmware** story that ADR-0006 says is "to be created": ESP-IDF, C, Unity tests, the framed UART protocol, Wi-Fi and 4G failover, its own certificate.

## Phase check
Phase 1 if ever rewritten. Read-only; polling never writes to a device.

## What would be kept if the story is rewritten rather than dropped
- "Each device is read on schedule (level and temperature every 1 s per NFR-01)" — a real requirement, now a firmware measurement-layer scheduling concern.
- "A silent device is flagged within 60 s" — a real requirement, now a sensor-health concern in firmware, matching the 60 s RTD flag in P1-06.
- "Tested against the simulator" — still applies (P1-02).

## Out of scope
Everything, until the backlog decision is made.

## Open questions
- `[Confirm]` Drop P1-11, or rewrite it as firmware scan scheduling and device-health flagging?
- `[Confirm]` Is Modbus needed anywhere in Phase 1? No ADR says yes.
- `[Confirm]` What happens to the `gateway/` folder, its CI job and its `pr-policy` scope?
