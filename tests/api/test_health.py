"""Health probe."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portpulse import __version__
from portpulse.app import create_app
from portpulse.config import get_settings, reset_settings_cache


def test_health_is_ok_when_datasets_are_readable(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "portpulse"
    assert body["version"] == __version__
    assert body["datasets_available"] is True
    assert body["watsonx_configured"] is False


def test_health_reports_503_when_datasets_are_missing(
    empty_data_dir: Path,
) -> None:
    reset_settings_cache()
    with TestClient(create_app(get_settings())) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_health_response_carries_a_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Request-ID"]


def test_inbound_request_id_is_echoed_back(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"


@pytest.mark.parametrize("path", ["/api/docs", "/api/openapi.json"])
def test_api_documentation_is_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200


def test_dashboard_is_served_at_the_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "PortPulse" in response.text
    assert "/api/v1" in response.text, "the dashboard must call the versioned API"
