from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from conftest import ALEMBIC_INI, alembic_config
from sqlalchemy import Engine, create_engine, inspect

from tankapi.db import Base

TABLES = {"scan_records", "readings", "gap_records"} | {
    "customers",
    "plants",
    "tanks",
    "devices",
    "device_assignments",
}


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_head_and_downgrade_base_run_cleanly_twice(database_url: str) -> None:
    config = alembic_config(database_url)
    for _ in range(2):
        command.upgrade(config, "head")
        assert table_names(database_url) == TABLES
        command.downgrade(config, "base")
        assert table_names(database_url) == set()


def test_models_match_the_migrated_schema(engine: Engine) -> None:
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_migration_renders_postgres_sql_offline() -> None:
    # No server: --sql mode only needs the dialect, which proves the DDL is Postgres-valid text.
    output = StringIO()
    config = Config(ALEMBIC_INI, output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql://")

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert {f"CREATE TABLE {table}" in sql for table in TABLES} == {True}
    assert "boot_id BYTEA NOT NULL" in sql and "id BIGSERIAL NOT NULL" in sql
    assert "CONSTRAINT uq_scan_records_device_id UNIQUE (device_id, boot_id, sequence)" in sql
    assert "CONSTRAINT ck_readings_value_matches_quality CHECK" in sql
    assert "CONSTRAINT ck_gap_records_lost_at_least_one CHECK (lost >= 1)" in sql
    assert "FOREIGN KEY(tank_id) REFERENCES tanks (id)" in sql
    assert "ON device_assignments (device_id) WHERE valid_to_unix_s IS NULL" in sql


def test_url_comes_from_the_environment_and_is_required(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TANKAPI_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="TANKAPI_DATABASE_URL"):
        command.upgrade(Config(ALEMBIC_INI), "head")

    monkeypatch.setenv("TANKAPI_DATABASE_URL", database_url)
    command.upgrade(Config(ALEMBIC_INI), "head")
    assert table_names(database_url) == TABLES
