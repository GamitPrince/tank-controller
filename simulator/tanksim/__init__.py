"""Tank-AI Phase 1 simulator (ADR-0004 decision 13).

A standalone Python simulator that produces every Phase 1 signal, so firmware,
cloud and dashboard work can be developed and tested with no hardware. Start it
with one command::

    python -m tanksim

Phase 1 is read-only monitoring of level and temperature. The simulator
produces readings, including the status of the hardwired safety-chain and alarm
contacts, which the controller only ever reads. It produces no command, no
setpoint and no output to the safety chain, and there is no inbound message
type in the record schema for one to travel in.

The contract it works to lives in ``interfaces/`` and is loaded at runtime: the
signal list (ADR-0004 decision 9) decides which signals exist and what their
ids, scales and wiring are, and the CDDL schema (decision 6) decides what a
record may contain. Nothing is duplicated here.

Module map:

``interfaces``  finding the shared contract folder
``signals``     loading and checking the signal list
``cddl``        validating a record against ``records.cddl``
``record``      building and encoding the CBOR scan record
``framing``     the COBS, sequence-number and CRC link frame (decision 5)
``clock``       the boot-relative clock that learns the wall clock (decision 11)
``plant``       plausible values for every signal, driven by the signal list
``faults``      injecting a sensor fault, an out-of-range value or a link drop
``link``        the outage buffer that replays with original timestamps
``device``      one scan: read, record, validate, frame, publish
``replay``      replaying a capture, timestamps untouched
``scaling``     linear scaling between a raw reading and an engineering value
``cli``         the one command
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
