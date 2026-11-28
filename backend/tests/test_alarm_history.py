"""The alarm history endpoint (S-091, P1-18).

TEST DATA ONLY. Every customer, tank, device, threshold and event here is made up.
Example Co (7) has tank 71 and Sample Ltd (8) tank 81; both have one radar threshold.
"""

import json
from collections.abc import Iterator

import access_tokens
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from test_alarm_thresholds import add, threshold

from tankapi import auth, session
from tankapi.alarm_history import MAX_EVENTS, MAX_RANGE_S
from tankapi.db import (
    AlarmAcknowledgementRow,
    AlarmEventRow,
    AuditRow,
    CustomerRow,
    PlantRow,
    ScanRow,
    TankRow,
)
from tankapi.main import app

EXAMPLE, SAMPLE = 7, 8
T = 1_763_683_200
STAFF = access_tokens.bearer(**{auth.GROUPS_CLAIM: ["service"], "sub": "staff-1"})
NOT_FOUND = {"detail": "not found"}


def customer(customer_id: int) -> dict[str, str]:
    claims = {auth.GROUPS_CLAIM: ["operator"], auth.CUSTOMER_CLAIM: str(customer_id)}
    return access_tokens.bearer(**claims)


def event(row_id: int, t: int | None, state: str = "high", threshold_id: int = 1) -> list:
    """A scan and the event judged from it; ``cannot_evaluate`` has a reason and no value:
    a fault, or ``time_unknown`` when the scan is untimed."""
    judged = state != "cannot_evaluate"
    row = AlarmEventRow(
        id=row_id,
        threshold_id=threshold_id,
        scan_record_id=row_id,
        unix_time_s=t,
        state=state,
        reason=None if judged else ("fault" if t is not None else "time_unknown"),
        value=18_100.0 if judged else None,
        quality=0 if judged else 3,
        limit_value=18_000,
        deadband=200,
    )
    header = {"device_id": "DEV-A", "signal_list_version": 1, "boot_id": bytes(16)}
    timed = {"time_known": t is not None, "unix_time_s": t}
    return [ScanRow(id=row_id, sequence=row_id, uptime_ms=row_id, **header, **timed), row]


def store(engine: Engine, *rows: object) -> None:
    """Add the scans first: the events refer to them."""
    add(engine, *(row for row in rows if isinstance(row, ScanRow)))
    add(engine, *(row for row in rows if not isinstance(row, ScanRow)))


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


def history(client: TestClient, tank: int = 71, headers: dict = STAFF, **params):
    query = {"from": T, "to": T + 3600} | params
    return client.get(f"/v1/tanks/{tank}/alarms", params=query, headers=headers)


def ids(response) -> list[int]:
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["events"]]


def test_an_empty_history_is_an_empty_list(client) -> None:
    response = history(client)
    expected = {"tank_id": 71, "from": T, "to": T + 3600, "events": [], "more": False}
    assert (response.status_code, response.json()) == (200, expected | {"untimed": 0})


def test_events_come_newest_first_with_what_was_judged(site, client) -> None:
    store(
        site, *event(1, T + 10), *event(2, T + 20, "normal"), *event(3, T + 30, "cannot_evaluate")
    )
    data = history(client).json()

    assert [item["id"] for item in data["events"]] == [3, 2, 1]
    assert data["events"][0] == {
        "id": 3,
        "t": T + 30,
        "threshold_id": 1,
        "measure": "signal",
        "signal_id": 1001,
        "direction": "high",
        "alarm_class": "warning",
        "limit": 18_000,
        "deadband": 200,
        "state": "cannot_evaluate",
        "reason": "fault",
        "value": None,
        "quality": "fault",
        "acknowledged": None,
    }
    assert (data["events"][2]["state"], data["events"][2]["value"]) == ("high", 18_100.0)
    assert data["events"][2]["quality"] == "good"


def test_events_at_one_second_keep_the_order_they_were_recorded_in(site, client) -> None:
    store(site, *event(1, T + 5), *event(2, T + 5, "normal"))
    assert ids(history(client)) == [2, 1]


def test_only_the_range_and_this_tank_are_returned(site, client) -> None:
    rows = event(1, T - 1) + event(2, T) + event(3, T + 3599) + event(4, T + 3600)
    store(site, *rows, *event(5, T + 10, threshold_id=2))
    assert ids(history(client)) == [3, 2]


def test_limit_keeps_the_newest_and_says_there_is_more(site, client) -> None:
    store(site, *(row for n in range(1, 6) for row in event(n, T + n)))
    response = history(client, limit=2)
    assert ids(response) == [5, 4]
    assert response.json()["more"] is True
    assert history(client, limit=5).json()["more"] is False


def test_an_untimed_event_is_counted_not_placed(site, client) -> None:
    store(site, *event(1, None, "cannot_evaluate"), *event(2, T + 1))
    data = history(client).json()
    assert ([item["id"] for item in data["events"]], data["untimed"]) == ([2], 1)


def test_a_customer_sees_their_own_tank(site, client) -> None:
    store(site, *event(1, T + 1))
    assert ids(history(client, headers=customer(EXAMPLE))) == [1]


@pytest.mark.parametrize("tank", [81, 999])
def test_another_customers_tank_answers_as_an_unknown_one(site, client, tank) -> None:
    store(site, *event(1, T + 1, threshold_id=2))
    response = history(client, tank=tank, headers=customer(EXAMPLE))
    assert (response.status_code, response.json()) == (404, NOT_FOUND)


def test_service_sees_any_tank_and_is_audited_with_the_tank(site, client) -> None:
    store(site, *event(1, T + 1, threshold_id=2))
    assert ids(history(client, tank=81, limit=10)) == [1]
    with Session(site) as db:
        [entry] = db.scalars(select(AuditRow)).all()
    assert (entry.route, entry.device_id, entry.status) == ("/v1/tanks/{tank_id}/alarms", None, 200)
    selected = {"tank_id": "81", "from": str(T), "to": str(T + 3600), "limit": "10"}
    assert json.loads(entry.query) == selected


def test_a_customer_request_is_not_audited(site, client) -> None:
    history(client, headers=customer(EXAMPLE))
    with Session(site) as db:
        assert db.scalars(select(AuditRow)).all() == []


def test_an_unknown_tank_is_not_found_for_service(client) -> None:
    response = history(client, tank=999)
    assert (response.status_code, response.json()) == (404, NOT_FOUND)


@pytest.mark.parametrize(
    "tank, params",
    [
        ("x", {}),
        (0, {}),
        (71, {"to": T}),  # from >= to
        (71, {"to": T + MAX_RANGE_S + 1}),
        (71, {"from": -1}),
        (71, {"limit": 0}),
        (71, {"limit": MAX_EVENTS + 1}),
        (71, {"limit": "many"}),
        (71, {"from": None}),
    ],
)
def test_bad_parameters_are_refused(client, tank, params) -> None:
    query = {"from": T, "to": T + 3600} | params
    query = {name: value for name, value in query.items() if value is not None}
    response = client.get(f"/v1/tanks/{tank}/alarms", params=query, headers=STAFF)
    assert response.status_code == 422


def test_the_widest_range_is_accepted(client) -> None:
    assert history(client, to=T + MAX_RANGE_S).status_code == 200


def test_no_token_is_refused(client) -> None:
    assert history(client, headers={}).status_code == 401


def test_the_route_reads_only(client) -> None:
    assert client.post("/v1/tanks/71/alarms", headers=STAFF).status_code == 405


def acknowledgement(event_id: int, note: str | None = None) -> AlarmAcknowledgementRow:
    return AlarmAcknowledgementRow(
        alarm_event_id=event_id, subject="user-1", role="maintenance", at_unix_ms=5, note=note
    )


def test_an_acknowledgement_is_shown_on_its_event_only(site, client) -> None:
    store(site, *event(1, T + 10), *event(2, T + 20, "low"), *event(3, T + 30))
    add(site, acknowledgement(1, "Seen."), acknowledgement(2))
    events = history(client, headers=customer(EXAMPLE)).json()["events"]

    assert [item["acknowledged"] for item in events] == [
        None,
        {"subject": "user-1", "role": "maintenance", "at": 5, "note": None},
        {"subject": "user-1", "role": "maintenance", "at": 5, "note": "Seen."},
    ]


def test_an_acknowledgement_stays_shown_after_the_alarm_clears(site, client) -> None:
    store(site, *event(1, T + 10), *event(2, T + 20, "normal"))
    add(site, acknowledgement(1))
    events = history(client).json()["events"]
    assert [(item["state"], item["acknowledged"] is None) for item in events] == [
        ("normal", True),
        ("high", False),
    ]


def test_acknowledgements_change_neither_the_limit_nor_the_counts(site, client) -> None:
    store(site, *(row for n in range(1, 4) for row in event(n, T + n)))
    store(site, *event(4, None, "cannot_evaluate"), *event(5, T + 5, threshold_id=2))
    add(site, *(acknowledgement(n) for n in (1, 2, 3, 5)))
    data = history(client, limit=2).json()
    assert ([item["id"] for item in data["events"]], data["more"], data["untimed"]) == (
        [3, 2],
        True,
        1,
    )
