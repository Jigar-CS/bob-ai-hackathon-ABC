"""Plan endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from portpulse.app import create_app
from portpulse.config import get_settings, reset_settings_cache

PLAN_URL = "/api/v1/plan"
CUSTOM_PLAN_URL = "/api/v1/plan/custom"
EXPORT_URL = "/api/v1/plan/export.csv"

VALID_VESSEL = {
    "vessel_id": "V001",
    "name": "MV Alpha",
    "eta": "2026-10-01 08:00",
    "size_teu": 5000,
    "cargo_type": "reefer",
    "priority": 1,
}
VALID_BERTH = {
    "berth_id": "B1",
    "capacity_teu": 16000,
    "crane_count": 4,
    "avg_dwell_hours": 6.0,
}


def test_get_plan_returns_every_section(client: TestClient) -> None:
    response = client.get(PLAN_URL)

    assert response.status_code == 200
    plan = response.json()
    assert set(plan) == {
        "generated_at",
        "freshness_status",
        "data_age_seconds",
        "source_name",
        "kpis",
        "congestion_forecast",
        "berth_assignments",
        "unassigned_count",
        "reroute_suggestions",
        "swap_opportunities",
        "weather_summary",
        "ml_enabled",
        "ml_allocation_used",
        "meta",
        "warnings",
    }
    assert len(plan["berth_assignments"]) == 3
    # weather_summary is always present; may be empty if weather disabled in test env
    assert isinstance(plan["weather_summary"], list)
    assert "effective_dwell_hours" in plan["berth_assignments"][0]


def test_get_plan_returns_503_with_guidance_when_datasets_are_missing(
    empty_data_dir: Path,
) -> None:
    reset_settings_cache()
    with TestClient(create_app(get_settings())) as client:
        response = client.get(PLAN_URL)

    assert response.status_code == 503
    assert "generate_sample_data.py" in response.json()["detail"]


def test_configuration_error_returns_500() -> None:
    from fastapi import FastAPI

    from portpulse.app import _register_exception_handlers
    from portpulse.errors import ConfigurationError

    app = FastAPI()
    _register_exception_handlers(app)

    @app.get("/test-config-error")
    async def _route():
        raise ConfigurationError("Test configuration exception")

    with TestClient(app) as client:
        response = client.get("/test-config-error")
        assert response.status_code == 500
        assert response.json()["detail"] == "A service configuration error occurred."


def test_custom_plan_accepts_validated_input(client: TestClient) -> None:
    response = client.post(
        CUSTOM_PLAN_URL, json={"vessels": [VALID_VESSEL], "berths": [VALID_BERTH]}
    )

    assert response.status_code == 200
    assert response.json()["berth_assignments"][0]["vessel_id"] == "V001"
    assert "effective_dwell_hours" in response.json()["berth_assignments"][0]


def test_custom_plan_rejects_a_bad_eta_format(client: TestClient) -> None:
    response = client.post(
        CUSTOM_PLAN_URL,
        json={"vessels": [{**VALID_VESSEL, "eta": "01/10/2026"}], "berths": [VALID_BERTH]},
    )

    assert response.status_code == 422
    assert "eta must match" in response.text


def test_custom_plan_rejects_out_of_range_priority(client: TestClient) -> None:
    response = client.post(
        CUSTOM_PLAN_URL,
        json={"vessels": [{**VALID_VESSEL, "priority": 9}], "berths": [VALID_BERTH]},
    )
    assert response.status_code == 422


def test_custom_plan_rejects_non_positive_size(client: TestClient) -> None:
    response = client.post(
        CUSTOM_PLAN_URL,
        json={"vessels": [{**VALID_VESSEL, "size_teu": 0}], "berths": [VALID_BERTH]},
    )
    assert response.status_code == 422


def test_custom_plan_rejects_empty_lists(client: TestClient) -> None:
    response = client.post(CUSTOM_PLAN_URL, json={"vessels": [], "berths": []})
    assert response.status_code == 422


def test_custom_plan_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        CUSTOM_PLAN_URL,
        json={"vessels": [{**VALID_VESSEL, "sneaky": "value"}], "berths": [VALID_BERTH]},
    )
    assert response.status_code == 422


def test_export_returns_csv_with_one_row_per_vessel(client: TestClient) -> None:
    response = client.get(EXPORT_URL)

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    lines = response.text.strip().splitlines()
    assert lines[0].startswith("vessel_id,vessel_name,status")
    assert "effective_dwell_hours" in lines[0]
    assert len(lines) == 4  # header + 3 vessels
    assert all("BERTHED" in line for line in lines[1:])
