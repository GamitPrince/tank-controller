"""The database session behind the HTTP endpoints (S-072).

The database URL comes from the ``TANKAPI_DATABASE_URL`` environment variable,
the same one the migrations read, so no URL is written in the repository. One
engine is built per URL and kept for the life of the process.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

DATABASE_URL_VARIABLE = "TANKAPI_DATABASE_URL"


@lru_cache(maxsize=1)
def _engine_for(url: str) -> Engine:
    return create_engine(url)


def get_engine() -> Engine:
    """The engine for ``TANKAPI_DATABASE_URL``; a missing URL is a server error."""
    url = os.environ.get(DATABASE_URL_VARIABLE)
    if not url:
        raise RuntimeError(f"{DATABASE_URL_VARIABLE} is not set")
    return _engine_for(url)


def get_session(engine: Annotated[Engine, Depends(get_engine)]) -> Iterator[Session]:
    """One session per request, closed when the response is sent."""
    with Session(engine) as session:
        yield session
