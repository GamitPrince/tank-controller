# P1-16: Remote access with no open inbound ports (card title: "Enforce VPN-only remote access")

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3. Points: 3. Priority: Must. Component: gateway (card); **now firmware, ESP32 and cloud**. Review flag: none.

## CONFLICT — the VPN requirement was overturned
The story card, RSD FR-COM-05 and NFR-05 all require "remote access only through VPN; no open internet access to field devices".

**ADR-0005 decided the opposite, deliberately:** outbound-only TLS, **no VPN in Phase 1**. ADR-0005's context records exactly this tension and resolves it — devices sit on the client's network, connect outbound to the broker, and accept nothing from outside. The security goal (nothing can reach the device from the internet) is met more strongly by having no inbound path at all than by a VPN.

The ADR is newer and merged, so it wins. `AGENTS.md` already lists FR-COM-05 and NFR-05 as needing rewording in the RSD. **This story should be retitled** to what is actually being built and verified: *no inbound path to field devices*. The RSD amendment is yours as project manager; I have not touched it.

## Phase check
Phase 1. Verification and configuration, not a new feature.

## Decisions already made
- **ADR-0005:** outbound-only TLS; no VPN in Phase 1; signed boot; **debug port locked on site units**; per-device certificates; broker block list; each device publishes only to its own topic.
- **ADR-0006:** secure boot and flash encryption on site ESP32 units.
- **ADR-0007:** AWS IoT Core with our own CA.

## Acceptance criteria (card, re-pointed to ADR-0005)
- An outside port scan finds **no open inbound ports** on field devices. **Still valid, and now the central criterion.**
- ~~Remote access works only through the VPN.~~ **Void.** Replace with: there is no remote access path to the device; service work is done on site, and Phase 1 firmware updates are by cable only (ADR-0007).
- **Every session is logged.** Re-point to the cloud-side audit trail (ADR-0008) and the broker connection log; there are no device sessions to log.
- Add: the debug port is locked on site units, and the lock is recorded per device.

## Test plan
Port scan the FRDM and the ESP32 from outside the plant network and from the same subnet. Attempt an inbound MQTT connection to the device. Attempt to connect with a revoked certificate and confirm the block list rejects it. Confirm the debug port is locked on a unit prepared as a site unit. Record all results — this is bench and site verification, not a unit test.

## Dependency
P1-12 (MQTT path must exist), the certificate and CA provisioning story that **does not yet exist**, and the ADR-0007 gates.

## Out of scope
Any VPN work. Phase 2 remote service access, if it is ever wanted.

## Open questions
- `[Confirm]` Retitle this story and amend RSD FR-COM-05 and NFR-05?
- `[Confirm]` Will Siemens or Astec accept no-VPN with outbound-only TLS? Their security review is the real test, and it is one of the ADR-0007 gate questions.
- `[Confirm]` Who runs the port scan, and does the client's IT need to be present?
