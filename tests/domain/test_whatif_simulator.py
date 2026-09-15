"""Unit tests for What-If scenario simulator."""

from __future__ import annotations

from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.whatif_simulator import simulate_whatif


def test_simulate_whatif_delay_vessel():
    vessels = load_vessels()
    berths = load_berths()

    scenario = {
        "type": "delay_vessel",
        "vessel_id": "V001",
        "delay_hours": 12.0,
    }

    result = simulate_whatif(vessels, berths, scenario)
    assert "baseline_plan" in result
    assert "modified_plan" in result
    assert "diff_summary" in result
    diff = result["diff_summary"]
    assert "reassigned_count" in diff
    assert "newly_unassigned_count" in diff


def test_simulate_whatif_berth_outage():
    vessels = load_vessels()
    berths = load_berths()

    scenario = {
        "type": "berth_outage",
        "berth_id": "B1",
        "hours": 24.0,
    }

    result = simulate_whatif(vessels, berths, scenario)
    assert "baseline_plan" in result
    assert "modified_plan" in result
    diff = result["diff_summary"]
    assert isinstance(diff["reassigned_vessels"], list)
