import logging
from pathlib import Path

import cbor2
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from tankapi.db import GapRow, ReadingRow, ScanRow
from tankapi.ingest import Accepted, IngestResult, Refused, device_from_topic, ingest_message

# The S-067 fixture: five simulator scans from device SIM-0001, seq 0 to 4.
PAYLOAD = bytes.fromhex(
    (Path(__file__).parent / "fixtures" / "simulator-batch-cbor-hex.txt").read_text()
)
TOPIC = "tank/SIM-0001/records"


def ingest(engine: Engine, topic: str, payload: bytes) -> IngestResult:
    with Session(engine) as session:
        return ingest_message(session, topic, payload)


def row_counts(engine: Engine) -> tuple[int, int, int]:
    with Session(engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (ScanRow, ReadingRow, GapRow)
        )


def with_device(index: int, device_id: str) -> bytes:
    """The fixture with one record's ``dev`` changed."""
    batch = cbor2.loads(PAYLOAD)
    batch[index]["dev"] = device_id
    return cbor2.dumps(batch)


def test_simulator_message_on_its_own_topic_is_stored(engine: Engine) -> None:
    assert ingest(engine, TOPIC, PAYLOAD) == Accepted(stored=5, skipped=0)
    assert row_counts(engine) == (5, 5 * 27, 0)


def test_same_message_twice_skips_everything_the_second_time(engine: Engine) -> None:
    ingest(engine, TOPIC, PAYLOAD)

    assert ingest(engine, TOPIC, PAYLOAD) == Accepted(stored=0, skipped=5)
    assert row_counts(engine) == (5, 5 * 27, 0)


@pytest.mark.parametrize(
    "topic",
    [
        "tank/SIM-0001",
        "tank/SIM-0001/records/extra",
        "/tank/SIM-0001/records",
        "tanks/SIM-0001/records",
        "Tank/SIM-0001/records",
        "tank/SIM-0001/record",
        "tank//records",
        "tank/" + "x" * 65 + "/records",
        "",
    ],
)
def test_wrong_topic_shape_is_refused_and_nothing_is_stored(engine: Engine, topic: str) -> None:
    result = ingest(engine, topic, PAYLOAD)

    assert isinstance(result, Refused)
    assert result.device_id is None
    assert "is not tank/<device id>/records" in result.reason
    assert row_counts(engine) == (0, 0, 0)


def test_device_id_follows_the_schema_rule_in_bytes() -> None:
    # 'é' is two bytes in UTF-8: 32 of them make 64 bytes, 33 make 66.
    assert device_from_topic("tank/" + "é" * 32 + "/records") == "é" * 32
    assert device_from_topic("tank/" + "é" * 33 + "/records") is None
    assert device_from_topic(b"tank/SIM-0001/records") is None


def test_topic_of_another_device_is_refused(engine: Engine) -> None:
    result = ingest(engine, "tank/SIM-0002/records", PAYLOAD)

    assert result == Refused(
        device_id="SIM-0002", reason="record 0: from device 'SIM-0001', not the topic's device"
    )
    assert row_counts(engine) == (0, 0, 0)


def test_one_foreign_record_refuses_the_whole_message(engine: Engine) -> None:
    result = ingest(engine, TOPIC, with_device(4, "SIM-0002"))

    assert isinstance(result, Refused)
    assert result.reason.startswith("record 4: from device 'SIM-0002'")
    assert row_counts(engine) == (0, 0, 0)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (b"\xff", "message: expected a batch array"),
        (PAYLOAD[:-1], "message: not valid CBOR"),
        (cbor2.dumps([]), "message: a batch holds 1 to 5 records, got 0"),
        (with_device(2, ""), "record 2: 'dev' must be text of 1 to 64 bytes"),
    ],
)
def test_malformed_payload_is_refused_with_the_decoder_reason(
    engine: Engine, payload: bytes, reason: str
) -> None:
    result = ingest(engine, TOPIC, payload)

    assert isinstance(result, Refused)
    assert result.device_id == "SIM-0001"
    assert result.reason.startswith(reason)
    assert row_counts(engine) == (0, 0, 0)


def test_refusal_leaves_a_stored_database_unchanged(engine: Engine) -> None:
    ingest(engine, TOPIC, PAYLOAD)
    batch = cbor2.loads(PAYLOAD)
    for record in batch:
        record["seq"] += 100  # new scans, which would be stored if accepted
    batch[0]["dev"] = "SIM-0002"

    assert isinstance(ingest(engine, TOPIC, cbor2.dumps(batch)), Refused)
    assert isinstance(ingest(engine, "tank/SIM-0001/x", PAYLOAD), Refused)
    assert row_counts(engine) == (5, 5 * 27, 0)


def test_refusal_is_logged_without_the_payload(
    engine: Engine, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    with caplog.at_level(logging.WARNING, logger="tankapi.ingest"):
        ingest(engine, "tank/SIM-0002/records", PAYLOAD)

    [entry] = caplog.records
    assert entry.levelno == logging.WARNING
    assert entry.getMessage() == (
        "refused message: device 'SIM-0002', record 0: from device 'SIM-0001', "
        f"not the topic's device, payload {len(PAYLOAD)} bytes"
    )
    assert PAYLOAD.hex() not in caplog.text
    assert repr(PAYLOAD)[:40] not in caplog.text
    assert capsys.readouterr() == ("", "")


def test_long_topic_is_cut_in_the_reason(engine: Engine) -> None:
    result = ingest(engine, "tank/" + "x" * 500, PAYLOAD)

    assert isinstance(result, Refused)
    assert len(result.reason) < 200
    assert "(507 characters)" in result.reason


def test_accepted_message_logs_no_refusal(engine: Engine, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="tankapi.ingest"):
        ingest(engine, TOPIC, PAYLOAD)

    assert caplog.records == []
