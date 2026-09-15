"""Berth assignment."""

from __future__ import annotations

import pytest

from portpulse.domain.assignment import assign_berths
from portpulse.errors import PlanningError

Row = dict[str, str]


def test_all_vessels_placed_when_capacity_allows(
    vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    result = assign_berths(vessel_rows, berth_rows)
    assert len(result.assigned) == 3
    assert result.unassigned == []
    assert all(record["wait_hours"] == 0 for record in result.assigned)


def test_priority_one_is_scheduled_first() -> None:
    vessels = [
        {
            "vessel_id": "LOW",
            "name": "Low",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "3",
        },
        {
            "vessel_id": "HIGH",
            "name": "High",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        },
    ]
    berths = [
        {"berth_id": "B1", "capacity_teu": "6000", "crane_count": "4", "avg_dwell_hours": "4.0"}
    ]
    result = assign_berths(vessels, berths)
    assert [record["vessel_id"] for record in result.assigned] == ["HIGH", "LOW"]
    assert result.assigned[0]["wait_hours"] == 0
    assert result.assigned[1]["wait_hours"] == 4.0


def test_queue_wait_is_measured_from_eta() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        },
        {
            "vessel_id": "V2",
            "name": "Two",
            "eta": "2026-10-01 09:00",
            "size_teu": "5000",
            "priority": "2",
        },
    ]
    berths = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "4", "avg_dwell_hours": "4.0"}
    ]
    result = assign_berths(vessels, berths)
    assert result.assigned[1]["wait_hours"] == 3.0
    assert result.assigned[1]["berth_start"] == "2026-10-01 12:00"
    assert "queued" in str(result.assigned[1]["reason"])


def test_vessel_larger_than_every_berth_is_unassigned() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "Giant",
            "eta": "2026-10-01 08:00",
            "size_teu": "25000",
            "priority": "1",
        }
    ]
    berths = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "4", "avg_dwell_hours": "6.0"}
    ]
    result = assign_berths(vessels, berths)
    assert result.assigned == []
    assert [row["vessel_id"] for row in result.unassigned] == ["V1"]


def test_wait_beyond_the_limit_makes_a_vessel_unassigned() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        },
        {
            "vessel_id": "V2",
            "name": "Two",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "2",
        },
    ]
    berths = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "4", "avg_dwell_hours": "20.0"}
    ]
    result = assign_berths(vessels, berths, max_wait_hours=12.0)
    assert len(result.assigned) == 1
    assert [row["vessel_id"] for row in result.unassigned] == ["V2"]


def test_unparseable_vessel_rows_are_reported_as_unassigned(berth_rows: list[Row]) -> None:
    vessels = [{"vessel_id": "V1", "name": "Broken", "eta": "whenever", "size_teu": "5000"}]
    result = assign_berths(vessels, berth_rows)
    assert result.assigned == []
    assert len(result.unassigned) == 1


def test_crane_count_and_priority_are_numeric(
    vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    record = assign_berths(vessel_rows, berth_rows).assigned[0]
    assert isinstance(record["crane_count"], int)
    assert isinstance(record["priority"], int)


def test_no_vessels_yields_empty_result(berth_rows: list[Row]) -> None:
    result = assign_berths([], berth_rows)
    assert result.assigned == []
    assert result.unassigned == []


@pytest.mark.parametrize(
    ("berths", "message"),
    [
        ([], "At least one berth"),
        ([{"berth_id": "B1", "capacity_teu": "oops"}], "No berth rows were usable"),
    ],
)
def test_unusable_berths_raise_planning_error(berths: list[Row], message: str) -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "100",
            "priority": "1",
        }
    ]
    with pytest.raises(PlanningError, match=message):
        assign_berths(vessels, berths)


def test_crane_count_fewer_than_baseline_lengthens_dwell() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        }
    ]
    # baseline_crane_count is 4 by default.
    # 2 cranes -> multiplier 4/2 = 2.0x -> effective dwell = 8.0
    berths = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "2", "avg_dwell_hours": "4.0"}
    ]
    res = assign_berths(vessels, berths)
    assigned = res.assigned[0]
    assert assigned["effective_dwell_hours"] == 8.0
    assert assigned["departure_est"] == "2026-10-01 16:00"
    assert "2 cranes (2.00x baseline dwell)" in str(assigned["reason"])


def test_crane_count_more_than_baseline_shortens_dwell() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        }
    ]
    # 8 cranes -> multiplier 4/8 = 0.5x -> effective dwell = 2.0
    berths = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "8", "avg_dwell_hours": "4.0"}
    ]
    res = assign_berths(vessels, berths)
    assigned = res.assigned[0]
    assert assigned["effective_dwell_hours"] == 2.0
    assert assigned["departure_est"] == "2026-10-01 10:00"
    assert "8 cranes (0.50x baseline dwell)" in str(assigned["reason"])


def test_crane_count_none_or_zero_falls_back_to_avg_dwell() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        }
    ]
    berths_none = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "", "avg_dwell_hours": "5.0"}
    ]
    res_none = assign_berths(vessels, berths_none)
    assert res_none.assigned[0]["effective_dwell_hours"] == 5.0
    assert "cranes" not in str(res_none.assigned[0]["reason"])

    berths_zero = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "0", "avg_dwell_hours": "5.0"}
    ]
    res_zero = assign_berths(vessels, berths_zero)
    assert res_zero.assigned[0]["effective_dwell_hours"] == 5.0


def test_crane_dwell_multiplier_clamping() -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "One",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "priority": "1",
        }
    ]
    # 1 crane -> baseline 4/1 = 4.0, clamped at max (default 2.0) -> dwell = 20.0
    berths_extreme_low = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "1", "avg_dwell_hours": "10.0"}
    ]
    res_low = assign_berths(vessels, berths_extreme_low)
    assert res_low.assigned[0]["effective_dwell_hours"] == 20.0

    # 50 cranes -> baseline 4/50 = 0.08, clamped at min (default 0.5) -> dwell = 5.0
    berths_extreme_high = [
        {"berth_id": "B1", "capacity_teu": "10000", "crane_count": "50", "avg_dwell_hours": "10.0"}
    ]
    res_high = assign_berths(vessels, berths_extreme_high)
    assert res_high.assigned[0]["effective_dwell_hours"] == 5.0
