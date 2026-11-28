from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

from tankapi.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_ok_and_the_installed_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("tankapi")}


def test_health_is_read_only(client: TestClient) -> None:
    response = client.post("/health")

    assert response.status_code == 405


def test_unknown_path_is_not_found(client: TestClient) -> None:
    response = client.get("/records")

    assert response.status_code == 404


def test_openapi_documents_get_paths_one_acknowledgement_and_the_version(client) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["version"] == version("tankapi")
    assert set(schema["paths"]) == {
        "/health",
        "/v1/devices/{device_id}/readings",
        "/v1/devices/{device_id}/latest",
        "/v1/tanks/{tank_id}/alarms",
        "/v1/alarms/{event_id}/acknowledgement",
    }
    # The one write is an acknowledgement, a cloud record only (S-092); the rest only read.
    methods = {path: set(found) for path, found in schema["paths"].items()}
    assert methods.pop("/v1/alarms/{event_id}/acknowledgement") == {"post"}
    assert all(found == {"get"} for found in methods.values())
