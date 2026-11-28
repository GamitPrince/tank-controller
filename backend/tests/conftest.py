import os
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, make_url, pool, text

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"

# S-098: a server login, for example postgresql+psycopg://tankai_dev@localhost:5432/postgres,
# with its password in pgpass.conf rather than in the URL. Unset, the Postgres runs are skipped.
TEST_DATABASE_URL_VARIABLE = "TANKAPI_TEST_DATABASE_URL"
# Created for each Postgres test and dropped after it; never a database that already exists.
TEST_DATABASE = "tankai_test"
SQLITE, POSTGRES = "sqlite", "postgresql"
TELEMETRY_OFF = "timescaledb.telemetry_level = 'off'"
TERMINATE_OWN_CONNECTIONS = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
    " WHERE datname = :database AND usename = current_user AND pid <> pg_backend_pid()"
)
# S-100's two policies: retention on reading_samples, refresh on reading_minutes.
TIMESCALE_JOBS = (
    "FROM timescaledb_information.jobs"
    " WHERE hypertable_name IN ('reading_samples', 'reading_minutes')"
)
# A policy run is a background worker on this database named after its policy.
POLICY_RUNNING = (
    "SELECT count(*) FROM pg_stat_activity"
    " WHERE datname = current_database() AND application_name LIKE '%Policy%'"
)
SETTLE_TIMEOUT_S = 30
POLL_S = 0.2


def alembic_config(url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    return config


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", f"postgres: run on SQLite and also on PostgreSQL ({TEST_DATABASE_URL_VARIABLE})"
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "database_url" in metafunc.fixturenames and metafunc.definition.get_closest_marker(
        "postgres"
    ):
        metafunc.parametrize("dialect", [SQLITE, POSTGRES])


@pytest.fixture
def dialect() -> str:
    """SQLite unless the test is marked ``postgres``, which runs it on both."""
    return SQLITE


@pytest.fixture
def database_url(dialect: str, tmp_path: Path) -> Iterator[str]:
    """A fresh, empty database per test, migrated by nothing yet."""
    if dialect == SQLITE:
        yield f"sqlite:///{tmp_path / 'tankapi.db'}"
    else:
        yield from _throwaway_postgres_database()


def _throwaway_postgres_database() -> Iterator[str]:
    server_url = os.environ.get(TEST_DATABASE_URL_VARIABLE)
    if not server_url:
        pytest.skip(f"{TEST_DATABASE_URL_VARIABLE} is not set")
    server = create_engine(server_url, isolation_level="AUTOCOMMIT", poolclass=pool.NullPool)
    with server.connect() as connection:
        # Fails if it exists, so a database left by someone else is never used or dropped.
        connection.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
        # S-100: TimescaleDB reports to its vendor by default; nothing leaves this machine.
        connection.execute(text(f"ALTER DATABASE {TEST_DATABASE} SET {TELEMETRY_OFF}"))
    try:
        url = make_url(server_url).set(database=TEST_DATABASE)
        yield url.render_as_string(hide_password=False)
    finally:
        with server.connect() as connection:
            # Only this login's leftover connections: WITH (FORCE) would also need the right
            # to end autovacuum workers, which a plain DROP DATABASE waits out by itself.
            connection.execute(text(TERMINATE_OWN_CONNECTIONS), {"database": TEST_DATABASE})
            connection.execute(text(f"DROP DATABASE {TEST_DATABASE}"))
        server.dispose()


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """An engine on a database built by the migrations, not by ``create_all``."""
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    if engine.dialect.name == SQLITE:
        event.listen(engine, "connect", _enforce_foreign_keys)
    elif has_timescale(engine):
        pause_timescale_policies(engine)
    yield engine
    engine.dispose()


def _enforce_foreign_keys(connection: sqlite3.Connection, _record: object) -> None:
    # SQLite checks foreign keys only when each connection asks; Postgres always does.
    connection.execute("PRAGMA foreign_keys = ON")


def has_timescale(engine: Engine) -> bool:
    with engine.connect() as db:
        query = text("SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'")
        return bool(db.scalar(query))


def pause_timescale_policies(engine: Engine) -> None:
    """Unschedule S-100's policies on this throwaway database and wait out a run in flight.

    The fixed test scans are older than 90 days, so a retention run the scheduler starts
    could drop their samples under a test (S-105). The policies stay in place, with their
    settings; a test that needs one runs it itself with ``CALL run_job``.
    """
    with engine.execution_options(isolation_level="AUTOCOMMIT").connect() as db:
        db.execute(text(f"SELECT alter_job(job_id, scheduled => false) {TIMESCALE_JOBS}"))
        deadline = time.monotonic() + SETTLE_TIMEOUT_S
        quiet_polls = 0
        # Twice quiet in a row, so a worker that was just starting is seen too.
        while quiet_polls < 2:
            assert time.monotonic() < deadline, "a TimescaleDB policy run never ended"
            quiet_polls = 0 if db.scalar(text(POLICY_RUNNING)) else quiet_polls + 1
            time.sleep(POLL_S)
