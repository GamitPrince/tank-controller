"""Alembic environment for the backend database (S-068).

The database URL comes from ``sqlalchemy.url`` when a caller sets it (the
tests do), otherwise from the ``TANKAPI_DATABASE_URL`` environment variable.
No URL or credential is written in this repository.
"""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from tankapi.db import Base

DATABASE_URL_VARIABLE = "TANKAPI_DATABASE_URL"

config = context.config


def database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get(DATABASE_URL_VARIABLE)
    if not url:
        raise RuntimeError(f"set {DATABASE_URL_VARIABLE} to the database URL")
    return url


def run_migrations_offline() -> None:
    """Write the SQL instead of running it (``alembic upgrade head --sql``)."""
    context.configure(url=database_url(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = engine_from_config(
        {"sqlalchemy.url": database_url()}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with engine.connect() as connection:
        # Batch mode lets later revisions alter tables on SQLite too.
        context.configure(
            connection=connection, target_metadata=Base.metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
