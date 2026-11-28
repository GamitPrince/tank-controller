import os
import sqlite3
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
    yield engine
    engine.dispose()


def _enforce_foreign_keys(connection: sqlite3.Connection, _record: object) -> None:
    # SQLite checks foreign keys only when each connection asks; Postgres always does.
    connection.execute("PRAGMA foreign_keys = ON")
