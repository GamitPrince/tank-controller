"""Decoding the CBOR batch message of ``interfaces/records.cddl`` (S-067).

One MQTT message on ``tank/{device_id}/records`` carries a batch of one to five
records, oldest first (S-062, S-064). Each is a scan record or a gap record,
complete on its own. :func:`decode_message` turns the bytes of one message into
typed records, or raises :class:`DecodeError` saying which record failed and
why. It does no I/O and stores nothing.

The whole message is checked before anything is returned, so a caller never
handles half a batch. Nothing is repaired: a faulted reading stays without a
value, an out-of-range value is kept as measured, and anything the schema does
not allow is refused rather than guessed at (AGENTS.md section 7).

``[Confirm]`` The checks below follow ``records.cddl`` field by field rather
than interpreting the schema file. ``tests/test_records_schema.py`` reads the
file and fails if the version or the quality codes here drift from it. A full
schema check shared with the simulator is a later story.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from io import BytesIO
from typing import Any

import cbor2

# `v: 1` in every record. Another version is refused, not read as this one.
RECORD_SCHEMA_VERSION = 1
# `batch = [1*5 message]`.
MAX_BATCH_RECORDS = 5
# `boot-id = bstr .size 16` and `device-id = tstr .size (1..64)`, in bytes.
BOOT_ID_BYTES = 16
DEVICE_ID_MAX_BYTES = 64


class Quality(IntEnum):
    """The per-reading quality codes, the `quality-values` group of the schema."""

    GOOD = 0
    STALE = 1
    OUT_OF_RANGE = 2
    FAULT = 3
    UNCONFIGURED = 4


# The schema sends no value for these; every other quality carries one.
QUALITIES_WITHOUT_VALUE = frozenset({Quality.FAULT, Quality.UNCONFIGURED})


class DecodeError(ValueError):
    """A message that does not match the record schema.

    ``record_index`` is the failing record's position in the batch, counting
    from 0, or ``None`` when the message as a whole is wrong.
    """

    def __init__(self, reason: str, record_index: int | None = None) -> None:
        self.reason = reason
        self.record_index = record_index
        where = "message" if record_index is None else f"record {record_index}"
        super().__init__(f"{where}: {reason}")


@dataclass(frozen=True)
class Reading:
    """One signal's value. ``value`` is ``None`` exactly when the quality has none."""

    signal_id: int
    quality: Quality
    age_ms: int
    value: int | bool | None


@dataclass(frozen=True)
class ScanRecord:
    """One sample of a set of signals, from one device, at one time."""

    device_id: str
    signal_list_version: int
    boot_id: bytes
    sequence: int
    uptime_ms: int
    time_known: bool
    unix_time_s: int | None
    readings: tuple[Reading, ...]


@dataclass(frozen=True)
class LostScan:
    """Where a dropped scan sat in time."""

    boot_id: bytes
    sequence: int
    uptime_ms: int
    time_known: bool
    unix_time_s: int | None


@dataclass(frozen=True)
class GapRecord:
    """Scans that were measured but will never arrive (S-040). Never interpolate across one."""

    device_id: str
    lost: int
    first: LostScan
    last: LostScan


Message = ScanRecord | GapRecord

_SCAN_KEYS = ({"v", "dev", "sl", "boot", "seq", "up", "tk", "r"}, {"t"})
_GAP_KEYS = ({"v", "dev", "gap"}, set())
_GAP_BODY_KEYS = ({"lost", "first", "last"}, set())
_LOST_SCAN_KEYS = ({"boot", "seq", "up", "tk"}, {"t"})
_READING_KEYS = ({"id", "q", "age"}, {"val"})


def decode_message(payload: bytes) -> tuple[Message, ...]:
    """Decode one MQTT message into its records, oldest first."""
    batch = _load_batch(payload)
    return tuple(_decode_record(item, index) for index, item in enumerate(batch))


def _load_batch(payload: bytes) -> list[Any]:
    if not isinstance(payload, bytes | bytearray):
        raise DecodeError(f"payload must be bytes, got {type(payload).__name__}")
    stream = BytesIO(payload)
    try:
        batch = cbor2.CBORDecoder(stream).decode()
    except cbor2.CBORDecodeError as error:
        raise DecodeError(f"not valid CBOR ({error})") from error
    if stream.tell() != len(payload):
        raise DecodeError(f"{len(payload) - stream.tell()} bytes follow the CBOR item")
    if not isinstance(batch, list):
        raise DecodeError(f"expected a batch array, got {type(batch).__name__}")
    if not 1 <= len(batch) <= MAX_BATCH_RECORDS:
        raise DecodeError(f"a batch holds 1 to {MAX_BATCH_RECORDS} records, got {len(batch)}")
    return batch


def _decode_record(item: Any, index: int) -> Message:
    try:
        if not isinstance(item, dict):
            raise DecodeError(f"expected a map, got {type(item).__name__}")
        version = item.get("v")
        if version != RECORD_SCHEMA_VERSION or isinstance(version, bool):
            raise DecodeError(f"unknown record version {version!r}")
        if "r" in item:
            return _decode_scan(item)
        if "gap" in item:
            return _decode_gap(item)
        raise DecodeError("neither a scan record (no 'r') nor a gap record (no 'gap')")
    except DecodeError as error:
        raise DecodeError(error.reason, index) from error


def _decode_scan(record: dict[Any, Any]) -> ScanRecord:
    _check_keys(record, _SCAN_KEYS, "scan record")
    readings = record["r"]
    if not isinstance(readings, list) or not readings:
        raise DecodeError("'r' must be a non-empty array of readings")
    time_known, unix_time_s = _time(record, "scan record")
    return ScanRecord(
        device_id=_device_id(record),
        signal_list_version=_uint(record, "sl", "scan record"),
        boot_id=_boot_id(record, "scan record"),
        sequence=_uint(record, "seq", "scan record"),
        uptime_ms=_uint(record, "up", "scan record"),
        time_known=time_known,
        unix_time_s=unix_time_s,
        readings=tuple(_decode_reading(entry, n) for n, entry in enumerate(readings)),
    )


def _decode_reading(entry: Any, position: int) -> Reading:
    where = f"reading {position}"
    _check_keys(entry, _READING_KEYS, where)
    signal_id = _uint(entry, "id", where)
    where = f"reading {position} (signal {signal_id})"
    code = _uint(entry, "q", where)
    try:
        quality = Quality(code)
    except ValueError:
        raise DecodeError(f"{where}: unknown quality {code}") from None
    value = entry.get("val")
    if "val" in entry and not isinstance(value, int):
        raise DecodeError(f"{where}: 'val' must be an integer or a bool")
    if quality in QUALITIES_WITHOUT_VALUE and "val" in entry:
        raise DecodeError(f"{where}: quality {quality.name.lower()} must carry no value")
    if quality not in QUALITIES_WITHOUT_VALUE and "val" not in entry:
        raise DecodeError(f"{where}: quality {quality.name.lower()} must carry a value")
    return Reading(signal_id, quality, _uint(entry, "age", where), value)


def _decode_gap(record: dict[Any, Any]) -> GapRecord:
    _check_keys(record, _GAP_KEYS, "gap record")
    body = record["gap"]
    _check_keys(body, _GAP_BODY_KEYS, "'gap'")
    lost = _uint(body, "lost", "'gap'")
    if lost < 1:
        raise DecodeError("'gap': 'lost' must be at least 1")
    return GapRecord(
        device_id=_device_id(record),
        lost=lost,
        first=_decode_lost_scan(body["first"], "'gap.first'"),
        last=_decode_lost_scan(body["last"], "'gap.last'"),
    )


def _decode_lost_scan(mark: Any, where: str) -> LostScan:
    _check_keys(mark, _LOST_SCAN_KEYS, where)
    time_known, unix_time_s = _time(mark, where)
    return LostScan(
        boot_id=_boot_id(mark, where),
        sequence=_uint(mark, "seq", where),
        uptime_ms=_uint(mark, "up", where),
        time_known=time_known,
        unix_time_s=unix_time_s,
    )


def _check_keys(value: Any, keys: tuple[set[str], set[str]], where: str) -> None:
    if not isinstance(value, dict):
        raise DecodeError(f"{where} must be a map, got {type(value).__name__}")
    required, optional = keys
    missing = sorted(required - value.keys())
    if missing:
        raise DecodeError(f"{where}: missing field {missing[0]!r}")
    unknown = sorted(repr(key) for key in value.keys() - required - optional)
    if unknown:
        raise DecodeError(f"{where}: unknown field {unknown[0]}")


def _uint(value: dict[Any, Any], key: str, where: str) -> int:
    number = value[key]
    if not isinstance(number, int) or isinstance(number, bool) or number < 0:
        raise DecodeError(f"{where}: {key!r} must be an unsigned integer, got {number!r}")
    return number


def _time(value: dict[Any, Any], where: str) -> tuple[bool, int | None]:
    time_known = value["tk"]
    if not isinstance(time_known, bool):
        raise DecodeError(f"{where}: 'tk' must be a bool, got {time_known!r}")
    if time_known != ("t" in value):
        state = "known" if time_known else "not known"
        raise DecodeError(f"{where}: 't' must be present exactly when 'tk' is true (time {state})")
    return time_known, _uint(value, "t", where) if time_known else None


def _boot_id(value: dict[Any, Any], where: str) -> bytes:
    boot_id = value["boot"]
    if not isinstance(boot_id, bytes) or len(boot_id) != BOOT_ID_BYTES:
        raise DecodeError(f"{where}: 'boot' must be {BOOT_ID_BYTES} bytes")
    return boot_id


def _device_id(record: dict[Any, Any]) -> str:
    device_id = record["dev"]
    if not isinstance(device_id, str) or not 1 <= len(device_id.encode()) <= DEVICE_ID_MAX_BYTES:
        raise DecodeError(f"'dev' must be text of 1 to {DEVICE_ID_MAX_BYTES} bytes")
    return device_id
