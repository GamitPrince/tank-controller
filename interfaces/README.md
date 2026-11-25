# `interfaces/` — the contract between the components

Everything in this folder is a contract that firmware, the simulator, the cloud
backend and the dashboard all read. Nothing here is owned by one component. A
change needs **one approval from a collaborator other than the author** (S-010),
and the `interfaces-review` check must be green.

| File | What it defines | Decision |
| --- | --- | --- |
| [`signals-v1.yaml`](signals-v1.yaml) | Every Phase 1 signal the device sends: numeric id, name, unit, scale, update rate, read-only flag, and per digital channel the contact sense and debounce. | [ADR-0004](../docs/adr/ADR-0004-communications-architecture.md) decision 9 |
| [`records.cddl`](records.cddl) | The CBOR scan record that carries those signals, and the gap record a device sends when its outage buffer had to drop scans that were never delivered (S-040). | [ADR-0004](../docs/adr/ADR-0004-communications-architecture.md) decisions 6 and 12 |

The signal list **replaces the register map** (ADR-0004 decision 9). Any
document still calling it a register map, including RSD FR-COM-01 and the `REG`
flag on story cards P1-04 to P1-08, is out of date.

## The version rule

The version lives in **both** the filename and a `version:` field inside the
file. The filename gives a device pinned to v1 a path that never changes
meaning; the field lets a parser check what it actually loaded and refuse a
mismatch.

**Within `signals-v1.yaml` you may, with one approval:**

- add a new signal with a new, never-before-used id;
- fill in or relax a `[Confirm]`, for example setting a real transducer range
  or tightening the temperature accuracy once the PT100 class is known;
- correct a description, or add a field that no consumer has to understand.

**Anything else needs a new `signals-v2.yaml`:**

- changing the meaning, unit, scale or class of an existing id;
- removing a signal, or reusing an id that once meant something else;
- renaming a signal, because `name` appears in code and in the API.

Ids are **never reused and never renumbered.** A signal that is retired keeps
its id and gains `retired_in: 2`; the id stays burnt. Id blocks: 1000 analogue,
2000 temperature, 3000 digital, 9000 device health.

`records.cddl` carries its version as the literal `v: 1` in the record itself,
so a consumer can reject a record it does not understand before parsing it. The
record's `sl` field says which signal-list version its ids come from, so the two
files version independently.

A record never carries a signal that is not in the signal list, and a consumer
must ignore an id it does not know rather than fail — that is what lets a device
on an older firmware keep reporting after the list gains a signal.

## What is deliberately not here

- **Volume, mass and level percent.** Computed in the cloud from these readings
  plus the tank geometry (ADR-0004 decision 10). The controller is send-only.
- **Modbus addresses, OPC UA node ids and the MQTT topic layout.** The topic
  layout is still undecided (`AGENTS.md` section 6).
- **Any command, setpoint or writable signal.** Phase 1 is read-only
  monitoring, and the hardwired safety chain is only ever read. A writable
  signal would be a phase change, not a signal-list edit.
- **Comparisons between signals.** Radar against pressure level, and the paired
  PT100s against each other, are Phase 2 mismatch checks.
- **Signals that exist at the site but are not wired to this board.** The
  over-temperature trip and the emergency stop are not routed to the
  controller, and there is no fire or gas input. A record or a screen must not
  imply a signal we do not monitor.

## Open `[Confirm]` items

These are recorded in the files themselves and in
[`docs/stories/P1-03-signal-list-v1.md`](../docs/stories/P1-03-signal-list-v1.md):

- the two 4-20 mA transducer ranges, so the cloud can convert loop current into
  a level;
- the PT100 class, which decides whether the accuracy target stays at 2.0 degC
  or tightens to 1.0 degC;
- `scan_interval_ms` on the digital channels, chosen here to fit the EE's
  debounce figures rather than measured;
- whether the three device-health signals are the set P1-02, P1-14 and P1-15
  want.
