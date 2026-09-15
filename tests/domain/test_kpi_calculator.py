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
