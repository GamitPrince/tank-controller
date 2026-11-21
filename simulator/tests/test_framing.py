"""Tests for the COBS, sequence-number and CRC link frame (ADR-0004 decision 5)."""

from __future__ import annotations

import random

import pytest

from tanksim.framing import (
    DELIMITER,
    FrameError,
    cobs_decode,
    cobs_encode,
    crc16_ccitt,
    decode_frame,
    encode_frame,
    split_frames,
)


def test_the_crc_matches_the_published_check_value():
    # CRC-16/CCITT-FALSE of "123456789" is 0x29B1. Checking against the
    # published value is what makes this interoperable with the firmware.
    assert crc16_ccitt(b"123456789") == 0x29B1


@pytest.mark.parametrize(
    "data",
    [
        b"\x01",
        b"\x00",
        b"\x00\x00",
        b"\x01\x00",
        b"\x00\x01",
        bytes(300),
        b"\xff" * 600,
        b"\x01" * 254,
        b"\x01" * 255,
        b"\x01" * 253 + b"\x00",
    ],
)
def test_cobs_round_trips_and_removes_every_zero(data):
    encoded = cobs_encode(data)
    assert DELIMITER not in encoded
    assert cobs_decode(encoded) == data


def test_cobs_round_trips_random_payloads():
    generator = random.Random(20261121)
    for length in range(0, 600, 7):
        data = bytes(generator.randrange(256) for _ in range(length))
        assert cobs_decode(cobs_encode(data)) == data


def test_a_zero_inside_an_encoded_frame_is_rejected():
    with pytest.raises(FrameError, match="must not contain a zero"):
        cobs_decode(b"\x02\x01\x00")


def test_a_group_running_past_the_end_is_rejected():
    with pytest.raises(FrameError, match="past the end"):
        cobs_decode(b"\x09\x01")


def test_a_frame_round_trips():
    frame = encode_frame(7, b"hello\x00world")
    assert frame.endswith(bytes([DELIMITER]))
    assert DELIMITER not in frame[:-1]
    decoded = decode_frame(frame)
    assert decoded.sequence == 7
    assert decoded.payload == b"hello\x00world"


def test_a_frame_decodes_without_its_delimiter():
    frame = encode_frame(1, b"payload")
    assert decode_frame(frame[:-1]).payload == b"payload"


def test_a_corrupt_frame_fails_its_crc():
    frame = bytearray(encode_frame(3, b"payload"))
    frame[4] ^= 0xFF
    with pytest.raises(FrameError, match="CRC mismatch"):
        decode_frame(bytes(frame))


def test_a_corrupt_sequence_number_fails_its_crc():
    # The CRC covers the sequence number too, so a frame whose sequence was
    # corrupted is rejected rather than acted on.
    frame = bytearray(encode_frame(3, b"payload"))
    frame[2] ^= 0x01
    with pytest.raises(FrameError, match="CRC mismatch"):
        decode_frame(bytes(frame))


def test_an_empty_payload_is_refused():
    with pytest.raises(FrameError, match="must carry a payload"):
        encode_frame(0, b"")


def test_a_negative_sequence_is_refused():
    with pytest.raises(FrameError, match="must not be negative"):
        encode_frame(-1, b"x")


def test_the_sequence_number_wraps():
    assert decode_frame(encode_frame(65536 + 3, b"x")).sequence == 3


def test_a_truncated_frame_is_refused():
    with pytest.raises(FrameError, match="too short"):
        decode_frame(cobs_encode(b"\x00\x01\x02"))


def test_a_stream_splits_into_its_frames():
    stream = encode_frame(1, b"a") + encode_frame(2, b"b")
    parts = split_frames(stream)
    assert [decode_frame(part).sequence for part in parts] == [1, 2]


def test_resynchronisation_after_line_noise():
    # Noise before the first delimiter becomes a candidate frame that fails its
    # CRC; the frames after it still decode.
    stream = b"\x05\x06\x07\x00" + encode_frame(9, b"good")
    parts = split_frames(stream)
    with pytest.raises(FrameError):
        decode_frame(parts[0])
    assert decode_frame(parts[-1]).payload == b"good"
