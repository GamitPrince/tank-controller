"""Acknowledging a raised alarm (S-093, P1-18).

TEST DATA ONLY. Every customer, tank, threshold, person and event here is made up.
Example Co (7) has tank 71 and Sample Ltd (8) tank 81; both have one radar threshold.
"""

import json
import time
from collections.abc import Iterator

import access_tokens
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_alarm_history import EXAMPLE, SAMPLE, STAFF, T, event, store
from test_alarm_thresholds import add, threshold

from tankapi import auth, session
from tankapi.db import (
    AlarmAcknowledgementRow,
    AlarmEventRow,
    AuditRow,
    CustomerRow,
    PlantRow,
    TankRow,
)
from tankapi.main import app

ROUTE = "/v1/alarms/{event_id}/acknowledgement"
NOT_FOUND = {"detail": "not found"}
NOT_RAISED = {"detail": "alarm not raised"}
ALREADY = {"detail": "already acknowledged"}


def person(role: str = "operator", customer_id: int = EXAMPLE) -> dict[str, str]:
    claims = {auth.GROUPS_CLAIM: [role], auth.CUSTOMER_CLAIM: str(customer_id)}
    return access_tokens.bearer(**claims)


@pytest.fixture
def site(engine: Engine) -> Engine:
    add(engine, *(CustomerRow(id=c, name=f"Customer {c}") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(PlantRow(id=c, customer_id=c, name="Plant A") for c in (EXAMPLE, SAMPLE)))
    add(engine, *(TankRow(id=n, plant_id=n // 10, name="Tank 1") for n in (71, 81)))
    add(engine, threshold(1, start=T - 100, tank_id=71), threshold(2, start=T - 100, tank_id=81))
    return engine


@pytest.fixture
def client(site: Engine) -> Iterator[TestClient]:
    app.dependency_overrides[session.get_engine] = lambda: site
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def acknowledge(client: TestClient, event_id: object = 1, headers: dict | None = None, **body):
    headers = person() if headers is None else headers
    return client.post(ROUTE.format(event_id=event_id), json=body, headers=headers)


def acknowledgements(engine: Engine) -> list[tuple]:
    with Session(engine) as db:
        rows = db.scalars(select(AlarmAcknowledgementRow)).all()
        return [(row.alarm_event_id, row.subject, row.role, row.note) for row in rows]


@pytest.mark.parametrize("role", ["operator", "maintenance", "admin"])
def test_a_customer_acknowledges_a_raised_alarm_at_server_time(site, client, role) -> None:
    store(site, *event(1, T + 10))
    before = time.time_ns() // 1_000_000
    response = acknowledge(client, headers=person(role), note="Seen, checking the radar.")
    after = time.time_ns() // 1_000_000

    assert response.status_code == 201, response.text
    data = response.json()
    assert before <= data.pop("at") <= after
    expected = {"event_id": 1, "subject": "user-1", "role": role}
    assert data == expected | {"note": "Seen, checking the radar."}
    assert acknowledgements(site) == [(1, "user-1", role, "Seen, checking the radar.")]


def test_a_note_is_optional_and_the_alarm_events_are_unchanged(site, client) -> None:
    store(site, *event(1, T + 10, "low"))
    assert acknowledge(client).json()["note"] is None
    with Session(site) as db:
        assert [(e.id, e.state) for e in db.scalars(select(AlarmEventRow))] == [(1, "low")]


def test_service_is_refused_and_the_attempt_is_audited(site, client) -> None:
    store(site, *event(1, T + 10))
    response = acknowledge(client, headers=STAFF)

    assert (response.status_code, response.json()) == (403, {"detail": "not allowed"})
    assert acknowledgements(site) == []
    with Session(site) as db:
        entry = db.scalars(select(AuditRow)).one()
    assert (entry.method, entry.route, entry.status) == ("POST", ROUTE, 403)
    assert json.loads(entry.query) == {"event_id": "1"}


def test_another_customers_alarm_answers_as_an_unknown_one(site, client) -> None:
    store(site, *event(1, T + 10, threshold_id=2))
    other = acknowledge(client)
    unknown = acknowledge(client, event_id=99)

    assert (other.status_code, other.json()) == (404, NOT_FOUND)
    assert (unknown.status_code, unknown.json()) == (404, NOT_FOUND)
    assert acknowledge(client, headers=person(customer_id=SAMPLE)).status_code == 201


def test_a_second_acknowledgement_is_refused_and_the_first_stands(site, client) -> None:
    store(site, *event(1, T + 10))
    acknowledge(client, note="first")
    response = acknowledge(client, headers=person("admin"), note="second")

    assert (response.status_code, response.json()) == (409, ALREADY)
    assert acknowledgements(site) == [(1, "user-1", "operator", "first")]


@pytest.mark.parametrize(
    ("later", "acknowledged"),
    [
        ((2, T + 20, "normal"), 1),  # cleared
        ((2, T + 20, "low"), 1),  # replaced by another raise
        ((2, T + 10, "normal"), 1),  # cleared in the same second, recorded later
        ((2, T + 10, "normal"), 2),  # a clear is not a raise
        ((2, T + 20, "cannot_evaluate"), 2),  # nor a value that could not be judged
    ],
)
def test_only_a_raise_still_in_force_is_acknowledged(site, client, later, acknowledged) -> None:
    store(site, *event(1, T + 10), *event(*later))
    response = acknowledge(client, event_id=acknowledged)

    assert (response.status_code, response.json()) == (409, NOT_RAISED)
    assert acknowledgements(site) == []


def test_a_raise_followed_only_by_cannot_evaluate_is_in_force(site, client) -> None:
    unjudged = event(2, T + 20, "cannot_evaluate") + event(3, None, "cannot_evaluate")
    store(site, *event(1, T + 10), *unjudged, *event(4, T + 30, "normal", threshold_id=2))
    assert acknowledge(client).status_code == 201


@pytest.mark.parametrize(
    "body", [{"note": ""}, {"note": "x" * 201}, {"note": 5}, {"silence": True}, [], "note"]
)
def test_a_bad_body_is_refused(site, client, body) -> None:
    store(site, *event(1, T + 10))
    response = client.post(ROUTE.format(event_id=1), json=body, headers=person())
    assert response.status_code == 422
    assert acknowledgements(site) == []


def test_a_missing_body_and_bad_event_ids_are_refused(site, client) -> None:
    store(site, *event(1, T + 10))
    assert client.post(ROUTE.format(event_id=1), headers=person()).status_code == 422
    for event_id in ("0", "-1", "abc"):
        assert acknowledge(client, event_id=event_id).status_code == 422


def test_a_note_of_the_largest_size_is_kept(site, client) -> None:
    store(site, *event(1, T + 10))
    assert acknowledge(client, note="x" * 200).status_code == 201


def test_no_token_is_refused(site, client) -> None:
    store(site, *event(1, T + 10))
    assert acknowledge(client, headers={}).status_code == 401
    assert acknowledgements(site) == []


def test_a_race_lost_in_the_database_answers_already_acknowledged(
    site, client, monkeypatch
) -> None:
    store(site, *event(1, T + 10))

    def lost_race(_self: Session) -> None:
        raise IntegrityError("INSERT", {}, Exception("unique"))

    monkeypatch.setattr(Session, "commit", lost_race)
    response = acknowledge(client)
    assert (response.status_code, response.json()) == (409, ALREADY)
