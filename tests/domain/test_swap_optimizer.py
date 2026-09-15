"""Unit tests for the berth swap optimizer module."""

from __future__ import annotations

from portpulse.domain.swap_optimizer import find_swap_opportunities


def test_find_swap_opportunities_empty():
    assert find_swap_opportunities([]) == []
    assert find_swap_opportunities([{"vessel_id": "V1"}]) == []


def test_find_swap_opportunities_detects_improving_swap():
    assignments = [
        {
            "vessel_id": "V001",
            "vessel_name": "MV Alpha",
            "berth_id": "B1",
            "priority": 3,
            "wait_hours": 0.0,
            "size_teu": 8000,
        },
        {
            "vessel_id": "V002",
            "vessel_name": "MV Beta",
            "berth_id": "B2",
            "priority": 1,
            "wait_hours": 4.5,
            "size_teu": 9000,
        },
    ]

    opps = find_swap_opportunities(assignments)
    assert len(opps) >= 1
    top = opps[0]
    assert top["hours_saved"] == 4.5
    # Recalculated cost saved: 4.5 hours * 8500 avg TEU * $0.05/TEU-hr = 1912.50
    assert top["estimated_cost_saved"] == 1912.50
    assert "MV Beta" in top["reason"] or "MV Alpha" in top["reason"]


def test_find_swap_opportunities_truncates_large_input():
    # 250 items
    assignments = [
        {
            "vessel_id": f"V{i:03d}",
            "vessel_name": f"MV Vessel {i}",
            "berth_id": "B1",
            "priority": 3,
            "wait_hours": 0.0,
            "size_teu": 5000,
        }
        for i in range(250)
    ]
    # Should not crash or take O(250^2)
    opps = find_swap_opportunities(assignments)
    assert isinstance(opps, list)
