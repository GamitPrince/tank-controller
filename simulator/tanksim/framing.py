"""The framed link protocol of ADR-0004 decision 5.

Decision 5 is our own framed protocol over the FRDM-to-ESP32 UART: COBS
framing, a sequence number and a CRC, with delivery confirmation on top. This
module implements the frame itself, so the simulator puts records on the wire
the way the real controller will.

Frame layout, before COBS encoding::

    sequence (2 bytes, big endian) | payload | CRC-16/CCITT-FALSE (2 bytes, BE)

COBS then removes every zero byte from that, and a single ``0x00`` delimiter
ends the frame. A reader can therefore resynchronise on a delimiter after any
amount of line noise, which is the reason for choosing COBS.

The CRC covers the sequence number as well as the payload, so a frame whose
sequence was corrupted is rejected rather than acted on.

``[Confirm]`` The sequence number is 16-bit and wraps. It is per boot, like the
record's own ``seq``, and the two are kept separate because the record counter
is the application's delivery confirmation while this one belongs to the link.
"""

from __future__ import annotations

from dataclasses import dataclass

# Frame delimiter. COBS guarantees the encoded bytes contain no zero, so a zero
# byte can only be a frame boundary.
DELIMITER = 0x00

SEQUENCE_BYTES = 2
CRC_BYTES = 2

# CRC-16/CCITT-FALSE: polynomial 0x1021, initial value 0xFFFF, no reflection,
# no final xor. Chosen because it is the variant the MCUXpresso and Zephyr CRC
# helpers both provide, so firmware needs no table of its own.
_CRC_POLYNOMIAL = 0x1021
_CRC_INITIAL = 0xFFFF
_SEQUENCE_MODULUS = 1 << (8 * SEQUENCE_BYTES)

# The most data bytes one COBS code byte can cover. A block of exactly this
# length is coded 255 and does not stand for a zero byte in the original data.
_COBS_MAX_BLOCK = 254


class FrameError(ValueError):
    """Raised when a frame cannot be built or is not intact."""


def crc16_ccitt(data: bytes) -> int:
    """CRC-16/CCITT-FALSE over ``data``."""
    crc = _CRC_INITIAL
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ _CRC_POLYNOMIAL) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """Consistent Overhead Byte Stuffing, without the trailing delimiter."""
    out = bytearray()
    block = bytearray()
    for byte in data:
        if byte != 0:
            block.append(byte)
            if len(block) == _COBS_MAX_BLOCK:
                # A full block is coded 255 and is not followed by a zero.
                out.append(255)
                out.extend(block)
                block.clear()
            continue
        out.append(len(block) + 1)
        out.extend(block)
        block.clear()
    out.append(len(block) + 1)
    out.extend(block)
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """Reverse :func:`cobs_encode`."""
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise FrameError("a COBS-encoded frame must not contain a zero byte")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise FrameError("COBS group runs past the end of the frame")
        out.extend(data[index:end])
        if code < 255 and end < len(data):
            out.append(0)
        index = end
    return bytes(out)


@dataclass(frozen=True)
class Frame:
    """A decoded link frame."""

    sequence: int
    payload: bytes


def encode_frame(sequence: int, payload: bytes) -> bytes:
    """Build one delimited frame carrying ``payload``.

    The sequence number wraps at :data:`SEQUENCE_BYTES` bytes rather than
    raising, because the real link counts frames for the life of a boot.
    """
    if not payload:
        raise FrameError("a frame must carry a payload")
    if sequence < 0:
        raise FrameError(f"frame sequence must not be negative, got {sequence}")
    header = (sequence % _SEQUENCE_MODULUS).to_bytes(SEQUENCE_BYTES, "big")
    body = header + payload
    body += crc16_ccitt(body).to_bytes(CRC_BYTES, "big")
    return cobs_encode(body) + bytes([DELIMITER])


def decode_frame(frame: bytes) -> Frame:
    """Decode one frame, with or without its trailing delimiter."""
    if frame.endswith(bytes([DELIMITER])):
        frame = frame[:-1]
    body = cobs_decode(frame)
    if len(body) <= SEQUENCE_BYTES + CRC_BYTES:
        raise FrameError("frame is too short to hold a sequence, a payload and a CRC")
    received = int.from_bytes(body[-CRC_BYTES:], "big")
    covered = body[:-CRC_BYTES]
    expected = crc16_ccitt(covered)
    if received != expected:
        raise FrameError(f"CRC mismatch: frame says {received:#06x}, computed {expected:#06x}")
    return Frame(
        sequence=int.from_bytes(covered[:SEQUENCE_BYTES], "big"),
        payload=covered[SEQUENCE_BYTES:],
    )


def split_frames(stream: bytes) -> list[bytes]:
    """Split a byte stream on the delimiter, dropping any empty run.

    A reader resynchronises this way after noise: everything between two
    delimiters is a candidate frame, and a corrupt one fails its CRC.
    """
    return [part for part in stream.split(bytes([DELIMITER])) if part]
