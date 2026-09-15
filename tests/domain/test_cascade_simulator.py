"""Unit tests for Cascading Impact simulator."""

from __future__ import annotations

from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.cascade_simulator import simulate_cascade


def test_simulate_cascade_berth_outage():
    vessels = load_vessels()
    berths = load_berths()

    disruption = {
        "type": "berth_outage",
        "berth_id": "B1",
        "hours": 24.0,
    }

    res = simulate_cascade(vessels, berths, disruption, max_iterations=5)
    assert res["iterations_run"] >= 1
    assert "stabilized" in res
    assert "total_vessels_affected" in res
    assert "total_cascade_delay_hours" in res
    assert "total_estimated_cost" in res
    assert isinstance(res["affected_vessels"], list)

    # Recomputed cost check at $0.05/TEU-hr
    expected_cost = sum(
        round(float(v["delay_hours"]) * int(v["size_teu"]) * 0.05, 2)
        for v in res["affected_vessels"]
    )
    assert res["total_estimated_cost"] == round(expected_cost, 2)


def test_simulate_cascade_delay_vessel():
    vessels = load_vessels()
    berths = load_berths()

    disruption = {
        "type": "delay_vessel",
        "vessel_id": "V001",
        "delay_hours": 10.0,
    }

    res = simulate_cascade(vessels, berths, disruption, max_iterations=3)
    assert res["iterations_run"] <= 3
    assert res["total_estimated_cost"] >= 0.0
