"""Ingesting one MQTT message (S-071).

:func:`ingest_message` is what a future queue consumer calls for each message a
device published on ``tank/{device_id}/records`` (ADR-0004 decision 7 and
amendment 4). It checks the topic, decodes the payload (S-067), checks that
every record came from the topic's device, and stores the records (S-070).

A message is either accepted, with how many records were stored and how many
were already stored, or refused, with a reason. A refused message writes
nothing, and the refusal is logged with the device ID, the reason and the
payload size, never the payload itself. Refusing is permanent: the same bytes
would be refused again, so a refusal is a result, not an exception. A database
failure is raised instead, so the caller can deliver the message again.

Each device publishes only to its own topic (ADR-0005), so a record whose
``dev`` is not the topic's device refuses the whole message: no record is ever
stored under a device it did not come from.

Phase 1: the controller is send-only, so ingest publishes nothing and answers
no device. Refused messages are not kept; a dead-letter store is a later story.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from tankapi.records import DEVICE_ID_MAX_BYTES, DecodeError, Message, decode_message
from tankapi.store import store_message

logger = logging.getLogger(__name__)

# `tank/{device_id}/records`: three topic levels, the device ID in the middle.
TOPIC_PREFIX = "tank"
TOPIC_SUFFIX = "records"
TOPIC_LEVELS = 3
# A refused topic is quoted in the reason; anything longer is cut, so a huge
# topic cannot flood the log.
MAX_QUOTED_TOPIC_CHARS = 100


@dataclass(frozen=True)
class Accepted:
    """The message was valid. ``stored`` records were written, ``skipped`` were already stored."""

    stored: int
    skipped: int


@dataclass(frozen=True)
class Refused:
    """The message was refused and nothing was written.

    ``device_id`` is the topic's device, or ``None`` when the topic has none.
    """

    device_id: str | None
    reason: str


IngestResult = Accepted | Refused


def ingest_message(session: Session, topic: str, payload: bytes) -> IngestResult:
    """Check, decode and store one MQTT message.

    The session must have no transaction open (see :func:`store_message`).
    """
    device_id = device_from_topic(topic)
    if device_id is None:
        return _refuse(None, f"topic {_quoted(topic)} is not tank/<device id>/records", payload)
    try:
        records = decode_message(payload)
    except DecodeError as error:
        return _refuse(device_id, str(error), payload)
    foreign = _first_foreign_record(records, device_id)
    if foreign is not None:
        index, other = foreign
        reason = f"record {index}: from device {other!r}, not the topic's device"
        return _refuse(device_id, reason, payload)
    stored = store_message(session, records)
    return Accepted(stored=stored.stored, skipped=stored.skipped)


def device_from_topic(topic: str) -> str | None:
    """The device ID of a ``tank/{device_id}/records`` topic, or ``None`` for any other topic.

    The device ID must meet the schema's ``device-id`` rule: 1 to 64 bytes of text.
    """
    if not isinstance(topic, str):
        return None
    levels = topic.split("/")
    if len(levels) != TOPIC_LEVELS or levels[0] != TOPIC_PREFIX or levels[2] != TOPIC_SUFFIX:
        return None
    device_id = levels[1]
    if not 1 <= len(device_id.encode()) <= DEVICE_ID_MAX_BYTES:
        return None
    return device_id


def _first_foreign_record(records: tuple[Message, ...], device_id: str) -> tuple[int, str] | None:
    for index, record in enumerate(records):
        if record.device_id != device_id:
            return index, record.device_id
    return None


def _refuse(device_id: str | None, reason: str, payload: bytes) -> Refused:
    size = len(payload) if isinstance(payload, bytes | bytearray) else None
    logger.warning("refused message: device %r, %s, payload %s bytes", device_id, reason, size)
    return Refused(device_id=device_id, reason=reason)


def _quoted(topic: object) -> str:
    text = repr(topic)
    if len(text) <= MAX_QUOTED_TOPIC_CHARS:
        return text
    return f"{text[:MAX_QUOTED_TOPIC_CHARS]}... ({len(text)} characters)"
