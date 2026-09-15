"""API tests for What-If scenario endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

WHATIF_URL = "/api/v1/plan/whatif"


def test_post_whatif_endpoint(client: TestClient) -> None:
    payload = {
        "scenario": {
            "type": "berth_outage",
            "berth_id": "B1",
            "hours": 24.0,
        }
    }
    response = client.post(WHATIF_URL, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "baseline_plan" in data
    assert "modified_plan" in data
    assert "diff_summary" in data
