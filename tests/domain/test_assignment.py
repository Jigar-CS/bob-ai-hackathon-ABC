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
