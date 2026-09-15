"""API tests for Cascading Impact simulation endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

CASCADE_URL = "/api/v1/cascade-simulation"


def test_post_cascade_endpoint(client: TestClient) -> None:
    payload = {
        "disruption": {
            "type": "berth_outage",
            "berth_id": "B1",
            "hours": 24.0,
        },
        "max_iterations": 5,
    }
    response = client.post(CASCADE_URL, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "iterations_run" in data
    assert "total_vessels_affected" in data
    assert "total_cascade_delay_hours" in data
    assert "total_estimated_cost" in data
    assert "affected_vessels" in data


def test_post_cascade_endpoint_rejects_bad_input(client: TestClient) -> None:
    payload = {
        "disruption": {
            "type": "unknown_type",
        },
    }
    response = client.post(CASCADE_URL, json=payload)
    assert response.status_code == 422
