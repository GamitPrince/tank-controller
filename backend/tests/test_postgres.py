"""What only a PostgreSQL server can show (S-098): TRUNCATE refused, and the backend role.

Skipped unless TANKAPI_TEST_DATABASE_URL is set (see conftest.py and backend/README.md).
The role ``tankapi_backend`` is made once by the database administrator; the grants come
from ``backend/sql/backend-role-grants.sql``, run here as the table owner would run it.
"""

from pathlib import Path

import pytest
from conftest import POSTGRES
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from test_db import AUDIT

pytestmark = pytest.mark.parametrize("dialect", [POSTGRES])

GRANTS = Path(__file__).parents[1] / "sql" / "backend-role-grants.sql"
ROLE = "tankapi_backend"
APPEND_ONLY = ["audit_entries", "alarm_events", "alarm_acknowledgements"]
GRANTED = {"SELECT", "INSERT"}
NOT_GRANTED = {"UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
INSERT_ENTRY = text(
    "INSERT INTO audit_entries (at_unix_ms, subject, role, method, route, device_id, query,"
    " status) VALUES (:at_unix_ms, :subject, :role, :method, :route, :device_id, :query,"
    " :status)"
)


def grant_statements() -> list[str]:
    lines = [line for line in GRANTS.read_text().splitlines() if not line.startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


@pytest.fixture
def granted(engine: Engine) -> Engine:
    with engine.begin() as db:
        if db.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": ROLE}) != 1:
            pytest.fail(f"role {ROLE} is missing: see backend/README.md")
        for statement in grant_statements():
            db.execute(text(statement))
    return engine


def as_backend(db: Connection) -> None:
    db.execute(text(f"SET LOCAL ROLE {ROLE}"))


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_the_owner_cannot_truncate_an_append_only_table(engine: Engine, table: str) -> None:
    # CASCADE gets past the foreign key that alone stops a plain TRUNCATE of alarm_events,
    # so only the triggers are left to refuse it (and, for alarm_events, its dependants').
    with pytest.raises(DBAPIError, match="is append-only"), engine.begin() as db:
        db.execute(text(f"TRUNCATE {table} CASCADE"))


def test_the_backend_role_may_only_add_and_read_audit_entries(granted: Engine) -> None:
    with granted.connect() as db:
        allowed = {
            privilege
            for privilege in GRANTED | NOT_GRANTED
            if db.scalar(
                text("SELECT has_table_privilege(:r, 'audit_entries', :p)"),
                {"r": ROLE, "p": privilege},
            )
        }
        owner = db.scalar(
            text("SELECT tableowner FROM pg_tables WHERE tablename = 'audit_entries'")
        )
    assert allowed == GRANTED
    assert owner != ROLE


def test_the_backend_role_adds_and_reads_an_entry(granted: Engine) -> None:
    with granted.begin() as db:
        as_backend(db)
        db.execute(INSERT_ENTRY, AUDIT)
        assert db.scalar(text("SELECT subject FROM audit_entries")) == "staff-1"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_entries SET status = 500",
        "DELETE FROM audit_entries",
        "TRUNCATE audit_entries",
    ],
)
def test_the_backend_role_is_denied_any_change(granted: Engine, statement: str) -> None:
    with granted.begin() as db:
        db.execute(INSERT_ENTRY, AUDIT)
    with pytest.raises(ProgrammingError, match="permission denied"), granted.begin() as db:
        as_backend(db)
        db.execute(text(statement))
    with granted.connect() as db:
        assert db.scalar(text("SELECT status FROM audit_entries")) == 200
