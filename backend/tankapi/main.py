"""The FastAPI application.

Phase 1 is read-only: the backend receives and serves plant data and never
sends a command to a device. This skeleton has only the health probe.
"""

from importlib.metadata import version

from fastapi import FastAPI
from pydantic import BaseModel

DISTRIBUTION_NAME = "tankapi"
HEALTH_OK = "ok"

# Read from the installed package metadata, so pyproject.toml is the one place
# the version is written. The app must be installed (pip install -e .).
APP_VERSION = version(DISTRIBUTION_NAME)


class Health(BaseModel):
    """What GET /health returns."""

    status: str
    version: str


app = FastAPI(title="Tank-AI backend", version=APP_VERSION)


# An operational probe for the container platform, so it sits outside the
# versioned REST API that ADR-0008 decision 7 asks for. [Confirm]
@app.get("/health")
def health() -> Health:
    """Report that the app is up, and which version is running."""
    return Health(status=HEALTH_OK, version=APP_VERSION)
