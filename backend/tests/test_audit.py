"""Every /v1 request by a service caller is in the append-only audit trail (S-080).

Every name is made up. DEV-A has one stored scan at T; DEV-NONE has nothing.
"""

import json
import logging
import time
from collections.abc import Callable, Iterator

import access_tokens
import cbor2
import pytest
from alembic import command
from conftest import alembic_config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from tankapi import auth, session
from tankapi.db import AuditRow
from tankapi.ingest import Accepted, ingest_message
from tankapi.main import app

T = 1_763_683_200
SIGNAL = 1001
RANGE = {"signal": SIGNAL, "from": T, "to": T + 60}
ROUTE = "/v1/devices/{device_id}/readings"
STAFF = {auth.GROUPS_CLAIM: ["service"], "sub": "staff-1"}


def store_scan(engine: Engine) -> None:
    reading = {"id": SIGNAL, "q": 0, "age": 1, "val": 5}
    scan = {"v": 1, "dev": "DEV-A", "sl": 1, "boot": bytes(16), "seq": 0, "up": 0}
    payload = cbor2.dumps([scan | {"tk": True, "t": T, "r": [reading]}])
    with Session(engine) as db:
        assert isinstance(ingest_message(db, "tank/DEV-A/records", payload), Accepted)


@pytest.fixture
def serve() -> Iterator[Callable[[Engine], TestClient]]:
    def client_on(engine: Engine) -> TestClient:
        app.dependency_overrides[session.get_engine] = lambda: engine
        app.dependency_overrides[auth.get_settings] = access_tokens.settings
        return TestClient(app, raise_server_exceptions=False)

    yield client_on
    app.dependency_overrides.clear()


@pytest.fixture
def client(serve: Callable[[Engine], TestClient], engine: Engine) -> TestClient:
    store_scan(engine)
    return serve(engine)


def read(client: TestClient, device: str = "DEV-A", params: dict = RANGE, **claims):
    headers = access_tokens.bearer(**(claims or STAFF))
    return client.get(f"/v1/devices/{device}/readings", params=params, headers=headers)


def entries(engine: Engine) -> list[AuditRow]:
    with Session(engine) as db:
        return list(db.scalars(select(AuditRow).order_by(AuditRow.id)))


def test_a_service_read_is_recorded_with_who_what_and_when(client, engine) -> None:
    before = time.time_ns() // 1_000_000
    assert read(client).status_code == 200

    [entry] = entries(engine)
    assert (entry.subject, entry.role, entry.method, entry.route) == (
        "staff-1",
        "service",
        "GET",
        ROUTE,
    )
    assert (entry.device_id, entry.status) == ("DEV-A", 200)
    assert json.loads(entry.query) == {"signal": str(SIGNAL), "from": str(T), "to": str(T + 60)}
    assert before <= entry.at_unix_ms <= time.time_ns() // 1_000_000


@pytest.mark.parametrize(
    ("device", "params", "status"),
    [
        ("DEV-NONE", RANGE, 404),
        ("DEV-A", RANGE | {"to": T}, 422),  # refused by the handler: from >= to
        ("DEV-A", {"from": T, "to": T + 60}, 422),  # refused by FastAPI: no signal
        ("D" * 100, RANGE | {"signal": "x" * 100}, 422),  # recorded cut to 64 characters
    ],
)
def test_a_refused_service_request_is_recorded_too(client, engine, device, params, status) -> None:
    assert read(client, device, params).status_code == status

    [entry] = entries(engine)
    assert (entry.device_id, entry.status) == (device[:64], status)
    assert json.loads(entry.query) == {name: str(value)[:64] for name, value in params.items()}


def test_a_service_request_that_fails_in_the_server_is_recorded_as_500(client, engine) -> None:
    def broken() -> None:
        raise RuntimeError("made-up failure")

    app.dependency_overrides[session.get_session] = broken
    assert read(client).status_code == 500
    assert [entry.status for entry in entries(engine)] == [500]


@pytest.mark.parametrize("role", ["operator", "maintenance", "admin"])
def test_a_customer_caller_is_not_recorded(client, engine, role) -> None:
    assert read(client, **{auth.GROUPS_CLAIM: [role]}).status_code == 404
    assert entries(engine) == []


def test_a_caller_refused_before_it_is_known_is_not_recorded(client, engine) -> None:
    assert client.get("/v1/devices/DEV-A/readings", params=RANGE).status_code == 401
    assert read(client, **{auth.GROUPS_CLAIM: ["service", "admin"]}).status_code == 403
    assert entries(engine) == []


def test_no_entry_holds_the_token_a_header_or_another_parameter(client, engine) -> None:
    token = access_tokens.token(**STAFF)
    headers = {"Authorization": f"Bearer {token}", "X-Note": "made-up header"}
    params = RANGE | {"access_token": token}
    assert client.get("/v1/devices/DEV-A/readings", params=params, headers=headers).is_success

    with engine.connect() as connection:
        row = " ".join(map(str, connection.execute(text("SELECT * FROM audit_entries")).one()))
    for secret in (token, token.split(".")[2], "Bearer", "made-up header", "access_token"):
        assert secret not in row


def test_a_service_request_whose_entry_cannot_be_written_is_refused(
    serve, database_url, caplog
) -> None:
    command.upgrade(alembic_config(database_url), "0003")  # no audit table to write to
    engine = create_engine(database_url)
    store_scan(engine)
    caplog.set_level(logging.ERROR, logger="tankapi.audit")

    response = read(serve(engine))
    engine.dispose()

    assert (response.status_code, response.json()) == (503, {"detail": "not available"})
    assert "audit entry of staff-1 on /v1/devices/{device_id}/readings not written" in caplog.text
    assert "Bearer" not in caplog.text
