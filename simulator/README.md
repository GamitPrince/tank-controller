# `simulator/` — the Tank-AI Phase 1 simulator

A standalone Python simulator that produces **every Phase 1 signal** so firmware,
cloud and dashboard work can be developed and tested with no hardware
([ADR-0004](../docs/adr/ADR-0004-communications-architecture.md) decision 13,
story P1-02).

Phase 1 is read-only monitoring of level and temperature. The simulator produces
readings, including the **status** of the hardwired safety-chain and alarm
contacts, which the controller only ever reads. It produces no command, no
setpoint and no output to the safety chain, and the record schema has no inbound
message type for one to travel in. `tests/test_phase_1_limits.py` checks that
rather than trusting it to the comments.

## One command

```sh
python -m tanksim
```

That loads `interfaces/signals-v1.yaml`, runs ten scans with no hardware and
prints a summary. Installed as a package it is also just `tanksim`.

Useful flags:

| Flag | What it does |
| --- | --- |
| `--output capture.bin` | write the framed byte stream a consumer actually reads |
| `--batches batches.txt` | write batch messages, one per line as hex: what the ESP32 publishes (S-095) |
| `--buffer-capacity N` | records the outage buffer holds; beyond it scans are lost and a gap record says so |
| `--scans N --interval-ms M` | how many scans, and the simulated gap between them |
| `--sntp-sync-after-ms N` | boot without a known wall clock, as a real device does |
| `--fault 2001:sensor_fault` | inject a sensor fault (also `out_of_range`, `stale`) |
| `--fault 1001:out_of_range@3-6` | limit a fault to a window of scan numbers |
| `--link-drop 4-8` | drop the cloud link for those scans |
| `--scenario faults.json` | the same faults from a file worth keeping |
| `--replay capture.bin` | replay a capture, timestamps untouched |

Examples:

```sh
python -m tanksim --scans 20 --fault 2003:sensor_fault@5-9 --output capture.bin
```

```sh
python -m tanksim --scans 20 --link-drop 5-12
```

A scenario file holds the same fields as the flags:

```json
{
  "signal_faults": [
    {"signal_id": 2001, "kind": "sensor_fault", "first_scan": 3, "last_scan": 6}
  ],
  "link_drops": [{"first_scan": 10, "last_scan": 14}]
}
```

## What it puts on the wire

Each scan reads every signal in the list, builds a CBOR record, **validates it
against `interfaces/records.cddl`** and frames it with COBS, a sequence number
and a CRC-16/CCITT-FALSE (ADR-0004 decisions 5 and 6). `--output` writes exactly
those bytes, so a consumer reads a capture with the same code it will use on the
real link.

Each reading carries a quality flag and an age (ADR-0008). A failed sensor is
flagged and **excluded, never silently replaced**: the reading keeps its id so a
screen can say the sensor failed, and carries no value at all.

`[Confirm]` The spec left open whether the simulator emulates the FRDM's UART
framed protocol or the ESP32's MQTT publish. This implements the FRDM side. It
needs no broker, no certificates and no cloud account — ADR-0007's three gates
have not been passed, so nothing here may open one — and an MQTT publisher is a
thin wrapper over the same frames, which belongs with the cloud stories (P1-14,
P1-15).

## Batch messages

A device does not publish one record at a time. The FRDM packs up to five
complete records, oldest first, into one link frame, and the ESP32 publishes
that frame unchanged as one MQTT message on `tank/{device_id}/records`
(S-062 to S-064). `--batches PATH` writes those messages, one per line as
lowercase hex of the CBOR array: exactly the payload the backend decodes
(S-067). Nothing is published to a broker or any network.

A batch is closed:

- after five messages, the steady state, one batch every 5 s;
- at once after a live scan that changes, against the scan before it, any
  reading's quality or value presence, or any digital contact's value (S-065),
  so an alarm or a sensor fault does not wait behind the timer;
- at the end of a run, as a shorter last batch.

After an outage the backlog drains oldest first, five to a batch, with its
original timestamps, and a change inside the backlog does not cut it. When the
outage buffer is full the lost scans arrive as one gap record after the buffered
ones (S-040). Every batch is checked against the schema's `batch` rule before it
is written. `--replay capture.bin --batches batches.txt` regroups an earlier
capture the same way.

```sh
python -m tanksim --scans 20 --link-drop 5-12 --buffer-capacity 4 --batches batches.txt
```

## Outage replay with the original timestamps

When the link drops, records go into a finite append-only buffer. When it comes
back they are delivered **unchanged**, each still carrying the uptime and Unix
time of the scan that produced it, in order. A consumer that stamped arrival
time instead would compress an outage into one instant and show buffered data as
live, which `AGENTS.md` section 7 forbids — replaying a capture is how you catch
that. `--replay` does the same for a capture taken earlier.

## Nothing about the plant is written in Python

The signal list decides which signals exist and what their ids, scales, units,
valid ranges, contact senses and debounce figures are; the CDDL schema decides
what a record may contain, down to the quality codes. Both are read at runtime
from `interfaces/`. If the YAML and the code disagree that is the bug this design
exists to prevent, so the tests run against the real contract, not a copy.
`TANKSIM_INTERFACES_DIR` overrides where it is found.

Adding a signal to the list therefore needs no code change: a signal the plant
model has no generator for is reported as `unconfigured`, not invented.

## How the CDDL criterion is met, and what is not proven

Story P1-03 deferred one acceptance criterion here: the CDDL schema must
validate a record the simulator produces. `tanksim/cddl.py` reads
`interfaces/records.cddl` at runtime, parses it with `cddlparser` and interprets
the syntax tree, so the rules are never duplicated in Python.

It covers the subset of CDDL the schema uses: maps with optional members, arrays
with an occurrence, rule references, the prelude types `uint`, `int`, `bool`,
`tstr` and `bstr`, literal values, type choices, `&` group choices and `.size`
with a plain size or a range. Anything outside that subset raises
`UnsupportedConstruct` when the schema is compiled, so unimplemented CDDL fails
loudly instead of passing silently.

`[Confirm]` This is **schema-driven structural validation, not a certified CDDL
implementation**. `pycddl` has no wheel for the Python version on the
development machine and building it needs a Rust toolchain, so it could not be
installed and the reference check was not run. Running `records.cddl` through a
full CDDL tool once one is installable — `pycddl` with Rust available, or the
Ruby `cddl` gem — would settle what this module can only check for the subset it
implements.

## Running the tests

The way CI does, from the repository root:

```sh
PYTHON=python bash scripts/ci/run-component.sh simulator
```

That builds a virtual environment, lints with ruff, runs pytest and enforces the
80% line-coverage gate over all of `tanksim`. The tests cover sensor failure,
out-of-range values, stale values, a link drop, a full buffer, a corrupt frame
and a record the schema forbids, not just the happy path.
