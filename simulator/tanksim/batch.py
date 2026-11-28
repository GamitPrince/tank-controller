"""Batch messages: what one MQTT message on ``tank/{device_id}/records`` holds.

On the wire a device sends a batch of one to five complete records, oldest
first (S-062): the FRDM packs them into one link frame (S-063) and the ESP32
publishes that frame unchanged (S-064). Steady scans go five to a batch, and a
scan that changes a contact or a quality goes at once (S-065), so an alarm does
not wait behind the 5 s timer.

:class:`BatchSink` takes the link's deliveries one record at a time and groups
them the same way. Each batch is checked against the schema's ``batch`` rule
before it leaves, so the simulator cannot write one the contract refuses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import cbor2

from .cddl import Schema
from .framing import decode_frame
from .link import Delivery
from .record import decode, default_schema
from .signals import SignalList

#: `batch = [1*5 message]` in ``interfaces/records.cddl``.
MAX_BATCH_MESSAGES = 5

#: Why a batch was closed.
CUT_FULL = "full"
CUT_CHANGE = "change"
CUT_END = "end"


class BatchError(ValueError):
    """Raised when a batch sink is configured impossibly."""


@dataclass(frozen=True)
class Batch:
    """One batch message, as the ESP32 would publish it."""

    #: The MQTT payload: one CBOR array of complete records, oldest first.
    payload: bytes
    count: int
    cut: str


def contact_ids(signal_list: SignalList) -> frozenset[int]:
    """The contacts S-065 compares: the digital inputs, not the health flags."""
    return frozenset(signal.id for signal in signal_list.in_group("digital"))


def _shape(reading: Mapping[str, Any]) -> tuple[Any, Any, bool]:
    return reading["id"], reading["q"], "val" in reading


def is_prompt_change(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    contacts: frozenset[int],
) -> bool:
    """S-065's rule: does ``current`` need to go out at once?

    It does when, against the scan before it, any reading's quality or value
    presence changed, any contact's value changed, or the scans do not line up.
    Analogue values move every scan, so they do not count. The first scan has
    nothing to compare with and counts as no change.
    """
    if previous is None:
        return False
    before, after = previous["r"], current["r"]
    if [_shape(r) for r in before] != [_shape(r) for r in after]:
        return True
    return any(
        old.get("val") != new.get("val")
        for old, new in zip(before, after, strict=True)
        if new["id"] in contacts
    )


class BatchSink:
    """A link sink that groups delivered records into batch messages."""

    def __init__(
        self,
        on_batch: Callable[[Batch], None],
        contact_ids: Iterable[int],
        schema: Schema | None = None,
        max_messages: int = MAX_BATCH_MESSAGES,
    ) -> None:
        if not 1 <= max_messages <= MAX_BATCH_MESSAGES:
            raise BatchError(
                f"a batch holds 1 to {MAX_BATCH_MESSAGES} messages, not {max_messages}"
            )
        self._on_batch = on_batch
        self._contacts = frozenset(contact_ids)
        self._schema = schema or default_schema()
        self._max = max_messages
        self._pending: list[dict[str, Any]] = []
        self._last_scan: dict[str, Any] | None = None

    def deliver(self, delivery: Delivery) -> None:
        """Add one record; close the batch when it is full or the record is a change."""
        message = decode(decode_frame(delivery.frame).payload, self._schema)
        self._pending.append(message)
        change = False
        if "r" in message:
            # A backlog drains five at a time (S-063), so only a live scan cuts early.
            change = not delivery.replayed and is_prompt_change(
                self._last_scan, message, self._contacts
            )
            self._last_scan = message
        if len(self._pending) >= self._max:
            self._emit(CUT_FULL)
        elif change:
            self._emit(CUT_CHANGE)

    def close(self) -> None:
        """Send what is left at the end of a run as a shorter last batch."""
        if self._pending:
            self._emit(CUT_END)

    def _emit(self, cut: str) -> None:
        batch = list(self._pending)
        self._schema.validate(batch, "batch")
        self._pending.clear()
        self._on_batch(Batch(payload=cbor2.dumps(batch), count=len(batch), cut=cut))
