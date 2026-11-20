# P1-13: Expose readings over OPC UA

- Story ID: `[Confirm]` — not yet issued.
- Epic: E3. Points: 5. Priority: Must in the RSD. Component: gateway (card). Review flag: none.
- Status: **Blocked on a decision. Do not start.**

## CONFLICT — no ADR covers OPC UA
RSD FR-COM-01 lists OPC UA as a Must, and the story card carries its own `[Confirm that OPC UA is needed in Phase 1]`. But **none of ADR-0004 to ADR-0009 mentions OPC UA at all.** ADR-0004 settled the communications architecture as framed UART, CBOR, MQTT over TLS to the cloud, and nothing else. The component it was assigned to, `gateway/`, no longer exists under ADR-0004 decision 1.

So there are two readings, and they lead to different work:

1. **OPC UA was dropped by ADR-0004 without being written down.** Then the RSD needs amending and this story moves to Phase 2 or is deleted. `AGENTS.md` already notes FR-COM-01 needs rewording.
2. **OPC UA is still required.** Then it needs an ADR of its own — where the server runs now that there is no gateway, which stack, how it is secured given ADR-0005 allows no inbound connections to field devices. A server listening for OPC UA clients is an **inbound** service, which sits awkwardly with ADR-0005's outbound-only rule and with P1-16's "no open inbound ports".

The second reading is close to a phase and security boundary question, so it is a tech lead plus EE decision, not a developer's.

## Phase check
Phase 1 only if reading 1 is rejected. Even then, read-only exposure; an OPC UA server must never expose a writable node.

## Acceptance criteria (from the story card, if it survives)
- An OPC UA client can browse and read all Phase 1 signals.
- The values match the MQTT values.

## Out of scope
Everything until the decision is made.

## Open questions
- `[Confirm]` Is OPC UA in Phase 1, Phase 2, or dropped?
- `[Confirm]` If kept: where does the server run, and how does it coexist with outbound-only and no open inbound ports?
- `[Confirm]` Who asked for OPC UA, and is it a customer requirement from Siemens or Astec?
