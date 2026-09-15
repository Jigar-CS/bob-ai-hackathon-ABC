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


def test_simulate_whatif_crane_count_impact():
    vessels = [
        {
            "vessel_id": "V1",
            "name": "A",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        },
        {
            "vessel_id": "V2",
            "name": "B",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "2",
        },
    ]
    # 2 cranes (8h dwell) vs 8 cranes (2h dwell)
    berths_slow = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "2", "avg_dwell_hours": "4.0"},
    ]
    scenario = {"type": "delay_vessel", "vessel_id": "V1", "delay_hours": 2.0}

    res_slow = simulate_whatif(vessels, berths_slow, scenario)
    assignment_v2_slow = res_slow["modified_plan"]["berth_assignments"][1]

    berths_fast = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "8", "avg_dwell_hours": "4.0"},
    ]
    res_fast = simulate_whatif(vessels, berths_fast, scenario)
    assignment_v2_fast = res_fast["modified_plan"]["berth_assignments"][1]

    # V2 waits longer when B1 has only 2 cranes than when B1 has 8 cranes
    assert assignment_v2_slow["wait_hours"] > assignment_v2_fast["wait_hours"]
