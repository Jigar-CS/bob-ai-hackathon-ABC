"""Unit tests for cargo type and berth capability matching."""

from __future__ import annotations

from portpulse.domain.assignment import _is_cargo_compatible, assign_berths
from portpulse.domain.swap_optimizer import find_swap_opportunities
from portpulse.ml.allocation_optimizer import allocate_with_ml


def test_is_cargo_compatible_helper():
    # Null or 'all' berth allows anything
    assert _is_cargo_compatible("limestone", None) is True
    assert _is_cargo_compatible("limestone", "") is True
    assert _is_cargo_compatible("limestone", "all") is True
    assert _is_cargo_compatible("limestone", "ALL") is True
    assert _is_cargo_compatible("limestone", "*") is True

    # Exact match & list of allowed types
    assert _is_cargo_compatible("limestone", "container, bulk, limestone") is True
    assert _is_cargo_compatible("hazmat", "container, bulk, limestone") is False
    assert _is_cargo_compatible("reefer", "reefer, container") is True
    assert _is_cargo_compatible("REEFER", "reefer, container") is True


def test_assign_berths_restricts_limestone_cargo():
    vessels = [
        {
            "vessel_id": "V_LIME",
            "name": "MV Limestone Carrier",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "cargo_type": "limestone",
            "priority": "1",
        }
    ]

    berths = [
        # B1 only accepts reefer & hazmat
        {
            "berth_id": "B1",
            "capacity_teu": "10000",
            "crane_count": "4",
            "avg_dwell_hours": "12.0",
            "allowed_cargo_types": "reefer, hazmat",
        },
        # B2 accepts bulk & limestone
        {
            "berth_id": "B2",
            "capacity_teu": "10000",
            "crane_count": "2",
            "avg_dwell_hours": "24.0",
            "allowed_cargo_types": "bulk, limestone",
        },
    ]

    res = assign_berths(vessels, berths)
    assert len(res.assigned) == 1
    # Must be assigned to B2 (compatible), NOT B1 (incompatible)
    assert res.assigned[0]["berth_id"] == "B2"
    assert "handling 'limestone'" in res.assigned[0]["reason"]


def test_ml_allocation_restricts_cargo():
    vessels = [
        {
            "vessel_id": "V_LIME",
            "name": "MV Limestone Carrier",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "cargo_type": "limestone",
            "priority": "1",
        }
    ]

    berths = [
        # B1 only accepts container
        {
            "berth_id": "B1",
            "capacity_teu": "10000",
            "crane_count": "4",
            "avg_dwell_hours": "12.0",
            "allowed_cargo_types": "container",
        },
        # B2 accepts limestone
        {
            "berth_id": "B2",
            "capacity_teu": "10000",
            "crane_count": "2",
            "avg_dwell_hours": "24.0",
            "allowed_cargo_types": "limestone",
        },
    ]

    res = allocate_with_ml(vessels, berths)
    assert len(res.assigned) == 1
    assert res.assigned[0]["berth_id"] == "B2"


def test_swap_optimizer_blocks_incompatible_cargo_swap():
    assignments = [
        {
            "vessel_id": "V1",
            "vessel_name": "MV Limestone",
            "berth_id": "B1",
            "size_teu": 5000,
            "priority": 1,
            "wait_hours": 10.0,
            "cargo_type": "limestone",
            "arrival": "2026-10-01 08:00",
            "departure_est": "2026-10-02 08:00",
        },
        {
            "vessel_id": "V2",
            "vessel_name": "MV Hazmat",
            "berth_id": "B2",
            "size_teu": 5000,
            "priority": 2,
            "wait_hours": 0.0,
            "cargo_type": "hazmat",
            "arrival": "2026-10-01 08:00",
            "departure_est": "2026-10-02 08:00",
        },
    ]

    berths = [
        # B1 accepts limestone
        {
            "berth_id": "B1",
            "capacity_teu": 10000,
            "crane_count": 2,
            "allowed_cargo_types": "limestone",
        },
        # B2 accepts hazmat only
        {
            "berth_id": "B2",
            "capacity_teu": 10000,
            "crane_count": 4,
            "allowed_cargo_types": "hazmat",
        },
    ]

    swaps = find_swap_opportunities(assignments, berths)
    # Swapping V1 (limestone) to B2 (hazmat only) is invalid and must return NO opportunities
    assert len(swaps) == 0
