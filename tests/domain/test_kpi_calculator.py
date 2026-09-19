"""Unit tests for the KPI calculation module."""

from __future__ import annotations

from portpulse.domain.kpi_calculator import calculate_plan_kpis


def test_calculate_plan_kpis_empty():
    plan = {
        "berth_assignments": [],
        "unassigned_count": 0,
        "congestion_forecast": [],
    }
    kpis = calculate_plan_kpis(plan)
    assert kpis["avg_wait_hours"] == 0.0
    assert kpis["berth_utilization_pct"] == 0.0
    assert kpis["vessels_at_risk"] == 0
    assert kpis["estimated_emissions_saved_kg"] == 0.0
    assert kpis["total_predicted_demurrage_usd"] == 0.0
    assert kpis["weather_delayed_vessels"] == 0


def test_calculate_plan_kpis_with_data():
    plan = {
        "berth_assignments": [
            {
                "vessel_id": "V001",
                "wait_hours": 2.0,
                "size_teu": 10000,
            },
            {
                "vessel_id": "V002",
                "wait_hours": 4.0,
                "size_teu": 8000,
            },
        ],
        "unassigned_count": 1,
        "congestion_forecast": [
            {"total_capacity_teu": 40000},
            {"total_capacity_teu": 40000},
        ],
    }
    kpis = calculate_plan_kpis(plan)
    assert kpis["avg_wait_hours"] == 3.0
    assert kpis["berth_utilization_pct"] == 45.0
    assert kpis["vessels_at_risk"] == 1
    assert kpis["estimated_emissions_saved_kg"] > 0
    assert kpis["total_predicted_demurrage_usd"] == 0.0  # no ML fields
    assert kpis["weather_delayed_vessels"] == 0


def test_ml_wait_hours_preferred_over_rule_based():
    """When predicted_wait_hours is present, avg_wait_hours uses ML values."""
    plan = {
        "berth_assignments": [
            {
                "vessel_id": "V001",
                "wait_hours": 0.0,
                "predicted_wait_hours": 3.0,
                "size_teu": 5000,
            },
            {
                "vessel_id": "V002",
                "wait_hours": 0.0,
                "predicted_wait_hours": 5.0,
                "size_teu": 6000,
            },
        ],
        "unassigned_count": 0,
        "congestion_forecast": [],
    }
    kpis = calculate_plan_kpis(plan)
    # Rule-based would give 0.0; ML gives (3+5)/2 = 4.0
    assert kpis["avg_wait_hours"] == 4.0


def test_weather_delayed_vessels_counted():
    plan = {
        "berth_assignments": [],
        "unassigned_count": 0,
        "congestion_forecast": [],
        "weather_summary": [
            {"vessel_id": "V001", "delay_hours": 9.0},
            {"vessel_id": "V002", "delay_hours": 4.0},
        ],
    }
    kpis = calculate_plan_kpis(plan)
    assert kpis["weather_delayed_vessels"] == 2


def test_total_predicted_demurrage_sums_ml_fields():
    plan = {
        "berth_assignments": [
            {
                "vessel_id": "V1",
                "wait_hours": 1.0,
                "size_teu": 5000,
                "predicted_demurrage_cost_usd": 250.0,
            },
            {
                "vessel_id": "V2",
                "wait_hours": 2.0,
                "size_teu": 6000,
                "predicted_demurrage_cost_usd": 400.0,
            },
            {"vessel_id": "V3", "wait_hours": 0.0, "size_teu": 3000},
        ],
        "unassigned_count": 0,
        "congestion_forecast": [],
    }
    kpis = calculate_plan_kpis(plan)
    assert kpis["total_predicted_demurrage_usd"] == 650.0
