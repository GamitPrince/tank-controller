import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


def alembic_config(url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """A fresh SQLite file per test, migrated by nothing yet."""
    return f"sqlite:///{tmp_path / 'tankapi.db'}"


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """An engine on a database built by the migrations, not by ``create_all``."""
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    event.listen(engine, "connect", _enforce_foreign_keys)
    yield engine
    engine.dispose()


def _enforce_foreign_keys(connection: sqlite3.Connection, _record: object) -> None:
    # SQLite checks foreign keys only when each connection asks; Postgres always does.
    connection.execute("PRAGMA foreign_keys = ON")
