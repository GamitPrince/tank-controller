"""Building and encoding the CBOR scan record of ``interfaces/records.cddl``.

ADR-0004 decision 6: records are CBOR described by that CDDL schema. Decision 9:
signals are identified by numeric id and a record carries one timestamp per
scan. Decision 11: time is SNTP where available, otherwise boot-relative, with a
boot id and a "time not yet known" flag. ADR-0008: every value carries a quality
flag and an age.

The quality codes are read out of the schema rather than written here, so there
is one definition of them in the project (see :class:`Quality`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import cbor2

from .cddl import Schema, load_schema

# The schema version this module writes. It is the literal `v: 1` in the record,
# and the schema itself checks it, so a mismatch fails validation rather than
# travelling.
RECORD_SCHEMA_VERSION = 1

# Length of the per-boot identifier, from `boot-id = bstr .size 16`.
BOOT_ID_BYTES = 16


class RecordError(ValueError):
    """Raised when a record cannot be built as the schema requires."""


class Quality:
    """The per-reading quality codes, read from the CDDL schema.

    ADR-0008 puts a quality flag on every value. The codes live in
    ``records.cddl`` as the ``quality-values`` group; this class exposes them by
    name so no Python file holds a second copy that could drift.
    """

    def __init__(self, schema: Schema) -> None:
        self._values = dict(schema.enum_values("quality-values"))

    def __getitem__(self, name: str) -> int:
        try:
            return int(self._values[name])
        except KeyError:
            raise RecordError(f"the schema defines no quality named {name!r}") from None

    @property
    def good(self) -> int:
        """Sampled normally, inside the valid range."""
        return self["good"]

    @property
    def stale(self) -> int:
        """Last known value, not refreshed this scan."""
        return self["stale"]

    @property
    def out_of_range(self) -> int:
        """Sampled, but outside the signal's ``valid_range``."""
        return self["out-of-range"]

    @property
    def fault(self) -> int:
        """Sensor or bus failure; no value is sent."""
        return self["fault"]

    @property
    def unconfigured(self) -> int:
        """Channel present in hardware but not commissioned."""
        return self["unconfigured"]

    @property
    def codes_without_value(self) -> frozenset[int]:
        """Qualities for which the schema expects ``val`` to be absent.

        A failed sensor is flagged and excluded, never silently replaced
        (AGENTS.md section 7), so these readings carry no number at all.
        """
        return frozenset({self.fault, self.unconfigured})


@lru_cache(maxsize=1)
def default_schema() -> Schema:
    """The compiled record schema, shared by every consumer in the process."""
    return load_schema()


@dataclass(frozen=True)
class Reading:
    """One signal's value in a scan record."""

    signal_id: int
    quality: int
    age_ms: int
    value: int | bool | None = None

    def to_record_map(self) -> dict[str, Any]:
        """The CBOR map for this reading, with ``val`` omitted when absent."""
        if self.age_ms < 0:
            raise RecordError(f"reading {self.signal_id} has a negative age")
        entry: dict[str, Any] = {"id": self.signal_id, "q": self.quality, "age": self.age_ms}
        if self.value is not None:
            entry["val"] = self.value
        return entry


@dataclass(frozen=True)
class ScanRecord:
    """One sample of a set of signals, from one device, at one time."""

    device_id: str
    signal_list_version: int
    boot_id: bytes
    sequence: int
    uptime_ms: int
    time_known: bool
    unix_time_s: int | None = None
    readings: tuple[Reading, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.boot_id) != BOOT_ID_BYTES:
            raise RecordError(f"boot id must be {BOOT_ID_BYTES} bytes, got {len(self.boot_id)}")
        if not self.readings:
            raise RecordError("a scan record must carry at least one reading")
        if self.time_known and self.unix_time_s is None:
            raise RecordError("time_known is true but no Unix time was given")
        if not self.time_known and self.unix_time_s is not None:
            raise RecordError("a Unix time was given while time_known is false")

    def to_record_map(self) -> dict[str, Any]:
        """The CBOR map for the whole record, in schema order."""
        record: dict[str, Any] = {
            "v": RECORD_SCHEMA_VERSION,
            "dev": self.device_id,
            "sl": self.signal_list_version,
            "boot": self.boot_id,
            "seq": self.sequence,
            "up": self.uptime_ms,
            "tk": self.time_known,
        }
        if self.unix_time_s is not None:
            record["t"] = self.unix_time_s
        record["r"] = [reading.to_record_map() for reading in self.readings]
        return record

    def encode(self, schema: Schema | None = None) -> bytes:
        """Validate against the CDDL schema, then encode as CBOR.

        Validating before encoding means the simulator cannot emit a record the
        contract does not allow, which is the P1-03 criterion this story carries.
        """
        record = self.to_record_map()
        (schema or default_schema()).validate(record)
        return cbor2.dumps(record)


def decode(payload: bytes, schema: Schema | None = None) -> dict[str, Any]:
    """Decode a CBOR record and validate it against the schema.

    This is the consumer side of the contract, used by the tests and by anyone
    reading a captured stream back.
    """
    record = cbor2.loads(payload)
    (schema or default_schema()).validate(record)
    return record
