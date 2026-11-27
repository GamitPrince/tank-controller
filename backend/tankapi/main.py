"""The FastAPI application.

Phase 1 is read-only: the backend receives and serves plant data and never
sends a command to a device. It serves the health probe (S-066) and, under
the ``/v1`` prefix, the read-only readings query (S-072). Every ``/v1`` route
sits on one router that checks the caller's token first (S-075) and records
every service caller's request in the audit trail (S-080); ``/health`` stays
open.
"""

from importlib.metadata import version

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel

from tankapi.audit import noting_requests, write_entries
from tankapi.auth import require_caller
from tankapi.readings import router as readings_router

DISTRIBUTION_NAME = "tankapi"
HEALTH_OK = "ok"

# Read from the installed package metadata, so pyproject.toml is the one place
# the version is written. The app must be installed (pip install -e .).
APP_VERSION = version(DISTRIBUTION_NAME)


class Health(BaseModel):
    """What GET /health returns."""

    status: str
    version: str


V1_PREFIX = "/v1"
v1 = APIRouter(
    prefix=V1_PREFIX,
    dependencies=[Depends(require_caller), Depends(noting_requests(V1_PREFIX))],
)
v1.include_router(readings_router)

app = FastAPI(title="Tank-AI backend", version=APP_VERSION)
app.middleware("http")(write_entries)
app.include_router(v1)


# An operational probe for the container platform, so it sits outside the
# versioned REST API that ADR-0008 decision 7 asks for. [Confirm]
@app.get("/health")
def health() -> Health:
    """Report that the app is up, and which version is running."""
    return Health(status=HEALTH_OK, version=APP_VERSION)
