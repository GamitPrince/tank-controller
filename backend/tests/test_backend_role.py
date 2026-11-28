"""The restricted backend role on every table (S-104).

``EXPECTED`` is the one decision per table that ``backend/sql/backend-role-grants.sql``
carries out. The guard runs everywhere, CI's SQLite included: a new table with no decision
fails it. The rest run only on PostgreSQL (TANKAPI_TEST_DATABASE_URL, see conftest.py), where
the script is checked against the catalogue and the backend's own code runs as the role.
TEST DATA ONLY. Every customer, tank, device, person and number here is made up.
"""

from collections.abc import Iterator

import access_tokens
import pytest
from conftest import POSTGRES
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, event, func, pool, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_alarm_recording import RADAR, SET, events, scan, send
from test_alarm_thresholds import add, threshold
from test_level_config import POINTS, chained, config
from test_level_config_edit import BODY as LEVEL_BODY
from test_postgres import GRANTS, ROLE, as_backend, grant_statements, granted  # noqa: F401  (a fixture)
from test_threshold_edit import BODY as THRESHOLD_BODY
from test_threshold_edit import person, seed, staff

from tankapi import auth, session
from tankapi.db import (
    AssignmentRow,
    AuditRow,
    Base,
    ConfigChangeRow,
    CustomerRow,
    DeviceRow,
    PlantRow,
    ScanRow,
    TankRow,
)
from tankapi.main import app

ON_POSTGRES = pytest.mark.parametrize("dialect", [POSTGRES])
READ, ADD = {"SELECT"}, {"SELECT", "INSERT"}
CLOSE = ADD | {"UPDATE (valid_to_unix_s)"}
APPEND_ONLY = ["audit_entries", "alarm_events", "alarm_acknowledgements", "config_changes"]
EXPECTED: dict[str, set[str]] = {
    "alembic_version": set(),
    "customers": READ,
    "plants": READ,
    "tanks": READ,
    "devices": READ,
    "device_assignments": READ,
    "scan_records": ADD,
    "readings": ADD,
    "reading_samples": ADD,
    "gap_records": ADD,
    "reading_minutes": set(),
    "alarm_thresholds": CLOSE,
    "level_configurations": CLOSE,
    "strapping_points": ADD,
} | {table: ADD for table in APPEND_ONLY}
# Each table that takes an INSERT and draws its id from a sequence.
SEQUENCES = {
    f"{table}_id_seq"
    for table in APPEND_ONLY
    + ["scan_records", "gap_records", "alarm_thresholds", "level_configurations"]
}
NOT_IN_MODELS = {"alembic_version", "reading_minutes"}
TABLE_ACL = (
    "SELECT c.relname, a.privilege_type FROM pg_class c"
    " JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'"
    " LEFT JOIN LATERAL aclexplode(c.relacl) a ON a.grantee = CAST(:role AS regrole)"
    " WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')"
)
COLUMN_ACL = (
    "SELECT c.relname, t.attname, a.privilege_type FROM pg_attribute t"
    " JOIN pg_class c ON c.oid = t.attrelid"
    " JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public',"
    " aclexplode(t.attacl) a WHERE a.grantee = CAST(:role AS regrole)"
)
OWNED = "SELECT count(*) FROM pg_class WHERE relowner = CAST(:role AS regrole)"
SEQUENCE_ACL = (
    "SELECT c.relname FROM pg_class c"
    " JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public',"
    " aclexplode(c.relacl) a WHERE c.relkind = 'S' AND a.grantee = CAST(:role AS regrole)"
    " AND a.privilege_type = 'USAGE'"
)


def test_every_table_has_a_grant_decision() -> None:
    assert set(Base.metadata.tables) == set(EXPECTED) - NOT_IN_MODELS
    script = GRANTS.read_text()
    assert all(table in script for table, rights in EXPECTED.items() if rights)


def held(db: Connection) -> dict[str, set[str]]:
    rights: dict[str, set[str]] = {}
    for table, privilege in db.execute(text(TABLE_ACL), {"role": ROLE}):
        rights.setdefault(table, set()).update({privilege} - {None})
    for table, column, privilege in db.execute(text(COLUMN_ACL), {"role": ROLE}):
        rights[table].add(f"{privilege} ({column})")
    return rights


@ON_POSTGRES
def test_the_role_holds_exactly_the_decided_rights(granted: Engine) -> None:  # noqa: F811
    with granted.begin() as db:
        assert held(db) == EXPECTED
        assert set(db.scalars(text(SEQUENCE_ACL), {"role": ROLE})) == SEQUENCES
        assert db.scalar(text(OWNED), {"role": ROLE}) == 0
        # A second run leaves the same rights.
        for statement in grant_statements():
            db.execute(text(statement))
        assert held(db) == EXPECTED


@ON_POSTGRES
@pytest.mark.parametrize("table", APPEND_ONLY)
@pytest.mark.parametrize("change", ["UPDATE {t} SET id = id WHERE false", "DELETE FROM {t}"])
def test_the_role_cannot_change_an_append_only_table(granted, table, change) -> None:  # noqa: F811
    refused(granted, change.format(t=table))


@ON_POSTGRES
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE alarm_thresholds SET limit_value = 0 WHERE false",
        "DELETE FROM alarm_thresholds",
        "DELETE FROM readings",
        "TRUNCATE scan_records CASCADE",
        "INSERT INTO tanks (plant_id, name) VALUES (1, 'Tank 9')",
        "SELECT * FROM alembic_version",
        "SELECT * FROM reading_minutes",
        "CREATE TABLE extra (id integer)",
        "ALTER TABLE readings ADD COLUMN extra integer",
        "CREATE INDEX extra ON readings (signal_id)",
        "DROP TRIGGER audit_entries_no_change ON audit_entries",
        "DROP TABLE strapping_points",
    ],
)
def test_the_role_is_refused_anything_else(granted: Engine, statement: str) -> None:  # noqa: F811
    refused(granted, statement)


def refused(engine: Engine, statement: str) -> None:
    denied = pytest.raises(ProgrammingError, match="permission denied|must be owner")
    with denied, engine.begin() as db:
        as_backend(db)
        db.execute(text(statement))


@pytest.fixture
def backend(granted: Engine) -> Iterator[Engine]:  # noqa: F811
    """The same database, every connection as the role, as the backend would connect."""
    engine = create_engine(granted.url, poolclass=pool.NullPool)
    event.listen(engine, "connect", _set_role)
    yield engine
    engine.dispose()


def _set_role(connection, _record: object) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {ROLE}")
    connection.commit()


@pytest.fixture
def client(granted: Engine, backend: Engine) -> Iterator[TestClient]:  # noqa: F811
    """Customer 1's tank 1 with DEV-A, a warning high of 18 mA and level configuration 1."""
    add(granted, CustomerRow(id=1, name="Example Co"), DeviceRow(device_id="DEV-A"))
    add(granted, PlantRow(id=1, customer_id=1, name="Plant A"))
    add(granted, TankRow(id=1, plant_id=1, name="Tank 1"))
    add(granted, AssignmentRow(device_id="DEV-A", tank_id=1, valid_from_unix_s=SET))
    seed(granted, threshold(1, deadband=500), config(1, 1, 1, SET))
    add(granted, *chained(1, POINTS))
    app.dependency_overrides[session.get_engine] = lambda: backend
    app.dependency_overrides[auth.get_settings] = access_tokens.settings
    yield TestClient(app)
    app.dependency_overrides.clear()


@ON_POSTGRES
def test_the_backend_runs_as_the_role(granted, backend, client) -> None:  # noqa: F811
    send(backend, scan(0, 17_000), scan(1, 19_000))
    assert [state for state, *_ in events(granted)] == ["high"]
    operator, admin = person("operator", 1), person("admin", 1)
    window = {"from": SET, "to": SET + 10}
    assert client.post("/v1/alarms/1/acknowledgement", json={}, headers=operator).status_code == 201
    reads = [
        client.get("/v1/tanks/1/alarms", params=window, headers=operator),
        client.get("/v1/devices/DEV-A/latest", headers=operator),
        client.get("/v1/devices/DEV-A/readings", params=window | {"signal": RADAR}, headers=admin),
    ]
    assert [response.status_code for response in reads] == [200, 200, 200]
    edits = [
        client.put("/v1/tanks/1/alarm-thresholds", json=THRESHOLD_BODY, headers=staff()),
        client.put("/v1/tanks/1/level-configuration", json=LEVEL_BODY, headers=admin),
    ]
    assert [response.status_code for response in edits] == [200, 200]
    with Session(granted) as db:
        assert db.scalar(select(func.count()).select_from(ScanRow)) == 2
        assert db.scalar(select(func.count()).select_from(ConfigChangeRow)) == 2
        assert db.scalar(select(func.count()).select_from(AuditRow)) == 1
