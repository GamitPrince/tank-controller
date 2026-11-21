"""The simulated device: one scan, one record, one frame.

This ties the pieces together the way the real controller will. Each scan reads
every signal in the list, turns each observation into a reading with a quality
flag and an age, builds a CBOR record, validates it against
``interfaces/records.cddl``, frames it (COBS, sequence number, CRC) and hands it
to the link.

Phase 1 limits, enforced by construction rather than by comment:

* the device has no method that writes a signal, sends a command or sets a
  setpoint, and the link carries nothing inbound, because the controller is
  send-only (ADR-0004 decision 10) and no command record exists in the schema;
* the safety-chain and alarm channels are read like any other status input;
* a failed sensor is flagged and excluded, never silently replaced, so a faulty
  reading carries no value at all (AGENTS.md section 7).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .cddl import Schema
from .clock import SimClock
from .faults import OUT_OF_RANGE, SENSOR_FAULT, STALE, FaultPlan, out_of_range_value
from .framing import encode_frame
from .link import BufferedLink
from .plant import PlantModel, PlantState
from .record import BOOT_ID_BYTES, Quality, Reading, ScanRecord, default_schema
from .signals import Signal, SignalList

#: Milliseconds between sampling the first signal of a scan and the record's
#: ``up``, used as each reading's ``age``. ``[Confirm]`` A real scan's age comes
#: from measuring it; a fixed per-signal step is enough to prove that consumers
#: carry the field through, and it keeps records reproducible.
DEFAULT_SAMPLE_STEP_MS = 1


class DeviceError(RuntimeError):
    """Raised when the device cannot produce a record."""


@dataclass(frozen=True)
class ScanResult:
    """What one scan produced."""

    record: ScanRecord
    frame: bytes
    delivered: bool
    replayed: int


def new_boot_id() -> bytes:
    """A random per-boot identifier, as ADR-0004 decision 11 requires."""
    return os.urandom(BOOT_ID_BYTES)


class SimulatedDevice:
    """A send-only device that publishes scan records with no hardware."""

    def __init__(
        self,
        device_id: str,
        signal_list: SignalList,
        link: BufferedLink,
        clock: SimClock,
        plant: PlantModel | None = None,
        fault_plan: FaultPlan | None = None,
        schema: Schema | None = None,
        boot_id: bytes | None = None,
        sample_step_ms: int = DEFAULT_SAMPLE_STEP_MS,
    ) -> None:
        if not device_id:
            raise DeviceError("a device id is required; it is the id in the commissioning QR code")
        self._device_id = device_id
        self._signals = signal_list
        self._link = link
        self._clock = clock
        self._plant = plant or PlantModel(signal_list)
        self._faults = fault_plan or FaultPlan()
        self._faults.validate_against(signal_list)
        self._schema = schema or default_schema()
        self._quality = Quality(self._schema)
        self._boot_id = boot_id if boot_id is not None else new_boot_id()
        self._sample_step_ms = max(0, sample_step_ms)
        self._sequence = 0
        self._scan = 0
        self._last_values: dict[int, int | bool] = {}

    @property
    def device_id(self) -> str:
        """The identifier the commissioning QR code carries (ADR-0005)."""
        return self._device_id

    @property
    def boot_id(self) -> bytes:
        """This boot's random identifier."""
        return self._boot_id

    @property
    def scans_done(self) -> int:
        """How many scans have run."""
        return self._scan

    # -- one scan ----------------------------------------------------------

    def scan(self) -> ScanResult:
        """Run one scan and publish its record."""
        scan_number = self._scan
        replayed = self._link.set_up(not self._faults.link_down(scan_number))

        state = PlantState(
            uptime_ms=self._clock.uptime_ms,
            uptime_s=self._clock.uptime_s,
            link_up=self._link.up,
            buffer_fraction=self._link.buffer_fraction,
        )
        readings = tuple(
            self._reading_for(signal, state, scan_number, position)
            for position, signal in enumerate(self._signals)
        )

        record = ScanRecord(
            device_id=self._device_id,
            signal_list_version=self._signals.version,
            boot_id=self._boot_id,
            sequence=self._sequence,
            uptime_ms=self._clock.uptime_ms,
            time_known=self._clock.time_known,
            unix_time_s=self._clock.unix_time_s,
            readings=readings,
        )
        frame = encode_frame(self._sequence, record.encode(self._schema))
        delivered = self._link.publish(frame, record.uptime_ms, record.unix_time_s)

        self._sequence += 1
        self._scan += 1
        return ScanResult(record=record, frame=frame, delivered=delivered, replayed=replayed)

    def run(self, scans: int, interval_ms: int) -> list[ScanResult]:
        """Run ``scans`` scans, advancing the clock by ``interval_ms`` between them."""
        if scans < 0:
            raise DeviceError(f"cannot run {scans} scans")
        results = []
        for index in range(scans):
            if index:
                self._clock.advance(interval_ms)
            results.append(self.scan())
        return results

    # -- turning an observation into a reading -----------------------------

    def _reading_for(
        self, signal: Signal, state: PlantState, scan_number: int, position: int
    ) -> Reading:
        age_ms = (len(self._signals) - position) * self._sample_step_ms
        fault = self._faults.kind_for(signal.id, scan_number)

        if fault == SENSOR_FAULT:
            # No value at all: a failed sensor is flagged and excluded.
            self._last_values.pop(signal.id, None)
            return Reading(signal_id=signal.id, quality=self._quality.fault, age_ms=age_ms)

        if fault == STALE:
            previous = self._last_values.get(signal.id)
            if previous is None:
                # Nothing has been read yet, so there is no last value to send.
                return Reading(signal_id=signal.id, quality=self._quality.fault, age_ms=age_ms)
            return Reading(
                signal_id=signal.id,
                quality=self._quality.stale,
                age_ms=age_ms,
                value=previous,
            )

        sample = self._plant.sample(signal, state)
        # The status decides first: a sample that reports a failure is a fault
        # even though it carries no value, and only a sample with nothing to
        # say at all falls through to unconfigured.
        if sample.status == "fault":
            return Reading(signal_id=signal.id, quality=self._quality.fault, age_ms=age_ms)
        if sample.status == "unconfigured" or sample.value is None:
            return Reading(signal_id=signal.id, quality=self._quality.unconfigured, age_ms=age_ms)

        if signal.is_boolean:
            value: int | bool = bool(sample.value)
            self._last_values[signal.id] = value
            return Reading(
                signal_id=signal.id, quality=self._quality.good, age_ms=age_ms, value=value
            )

        engineering = float(sample.value)
        quality = self._quality.good
        if fault == OUT_OF_RANGE:
            low, high = signal.valid_range  # checked by FaultPlan.validate_against
            engineering = out_of_range_value(low, high)
            quality = self._quality.out_of_range
        elif signal.valid_range is not None:
            low, high = signal.valid_range
            if not low <= engineering <= high:
                quality = self._quality.out_of_range

        raw = signal.to_raw(engineering)
        self._last_values[signal.id] = raw
        return Reading(signal_id=signal.id, quality=quality, age_ms=age_ms, value=raw)
