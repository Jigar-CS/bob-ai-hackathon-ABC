"""API key protection and startup safety guards."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portpulse.app import create_app
from portpulse.config import get_settings, reset_settings_cache
from portpulse.errors import ConfigurationError

API_KEY = "test-secret-key"
CUSTOM_PLAN_URL = "/api/v1/plan/custom"
PAYLOAD = {
    "vessels": [
        {
            "vessel_id": "V001",
            "name": "MV Alpha",
            "eta": "2026-10-01 08:00",
            "size_teu": 5000,
            "cargo_type": "reefer",
            "priority": 1,
        }
    ],
    "berths": [{"berth_id": "B1", "capacity_teu": 16000, "crane_count": 4, "avg_dwell_hours": 6.0}],
}


@pytest.fixture
def secured_client(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("PORTPULSE_API_KEY", API_KEY)
    reset_settings_cache()
    with TestClient(create_app(get_settings())) as client:
        yield client


def test_write_endpoint_requires_a_key_when_one_is_configured(
    secured_client: TestClient,
) -> None:
    response = secured_client.post(CUSTOM_PLAN_URL, json=PAYLOAD)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key."


def test_write_endpoint_rejects_a_wrong_key(secured_client: TestClient) -> None:
    response = secured_client.post(CUSTOM_PLAN_URL, json=PAYLOAD, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_write_endpoint_accepts_the_configured_key(secured_client: TestClient) -> None:
    response = secured_client.post(CUSTOM_PLAN_URL, json=PAYLOAD, headers={"X-API-Key": API_KEY})
    assert response.status_code == 200


def test_read_endpoints_stay_public(secured_client: TestClient) -> None:
    assert secured_client.get("/health").status_code == 200
    assert secured_client.get("/api/v1/plan").status_code == 200


def test_uploads_are_also_protected(secured_client: TestClient) -> None:
    response = secured_client.post(
        "/api/v1/uploads/vessels",
        files={"file": ("v.csv", b"vessel_id\nV1\n", "text/csv")},
    )
    assert response.status_code == 401


def test_write_endpoints_are_open_without_a_configured_key(client: TestClient) -> None:
    """Local development convenience: no key configured means no gate."""
    assert client.post(CUSTOM_PLAN_URL, json=PAYLOAD).status_code == 200


def test_cors_defaults_to_localhost_only(client: TestClient) -> None:
    settings = get_settings()
    assert settings.app.cors_origins == [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    assert "*" not in settings.app.cors_origins


def test_production_refuses_to_start_without_an_api_key(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORTPULSE_ENVIRONMENT", "production")
    monkeypatch.delenv("PORTPULSE_API_KEY", raising=False)
    reset_settings_cache()

    with (
        pytest.raises(ConfigurationError, match="PORTPULSE_API_KEY must be set"),
        TestClient(create_app(get_settings())),
    ):
        pass  # pragma: no cover - startup raises before the body runs


def test_production_refuses_wildcard_cors(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORTPULSE_ENVIRONMENT", "production")
    monkeypatch.setenv("PORTPULSE_API_KEY", API_KEY)
    monkeypatch.setenv("PORTPULSE_CORS_ALLOW_ORIGINS", "*")
    reset_settings_cache()

    with (
        pytest.raises(ConfigurationError, match="Wildcard CORS"),
        TestClient(create_app(get_settings())),
    ):
        pass  # pragma: no cover


def test_chat_endpoint_protected_when_key_configured(secured_client: TestClient) -> None:
    plan = {
        "generated_at": "2026-09-25T00:00:00",
        "congestion_forecast": [],
        "berth_assignments": [],
        "unassigned_count": 0,
        "reroute_suggestions": [],
        "warnings": [],
    }
    chat_payload = {"message": "Which vessel is at B1?", "plan": plan, "history": []}
    res = secured_client.post("/api/v1/chat", json=chat_payload)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid or missing API key."

    res_ok = secured_client.post("/api/v1/chat", json=chat_payload, headers={"X-API-Key": API_KEY})
    assert res_ok.status_code == 200


def test_security_headers_present_on_responses(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_reset_whatif_cascade_protected_when_key_configured(secured_client: TestClient) -> None:
    res1 = secured_client.post("/api/v1/datasets/reset")
    assert res1.status_code == 401

    res2 = secured_client.post(
        "/api/v1/plan/whatif",
        json={"scenario": {"type": "berth_outage", "berth_id": "B1", "hours": 12.0}},
    )
    assert res2.status_code == 401

    res3 = secured_client.post(
        "/api/v1/cascade-simulation",
        json={"disruption": {"type": "berth_outage", "berth_id": "B1", "hours": 12.0}},
    )
    assert res3.status_code == 401
