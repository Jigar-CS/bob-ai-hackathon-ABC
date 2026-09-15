"""Plan orchestration and partial-failure behaviour."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from portpulse.domain import planner
from portpulse.domain.planner import generate_ops_plan
from portpulse.errors import PlanningError
from portpulse.schemas import OpsPlan

Row = dict[str, str]

# Fixed reference time so test vessel ETAs (Oct 2026) fall inside the horizon.
_NOW = datetime(2026, 10, 1, 8, 0)


def test_plan_contains_every_section(
    settings: Any, vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    plan = generate_ops_plan(vessel_rows, berth_rows, now=_NOW)

    assert plan["congestion_forecast"]
    assert len(plan["berth_assignments"]) == 3
    assert plan["unassigned_count"] == 0
    assert plan["reroute_suggestions"] == []
    assert plan["warnings"] == []
    assert plan["generated_at"].endswith("+00:00")


def test_plan_validates_against_the_response_schema(
    settings: Any, vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    """Guards against the domain layer and the API contract drifting apart."""
    OpsPlan.model_validate(generate_ops_plan(vessel_rows, berth_rows, now=_NOW))


def test_oversized_vessels_flow_into_reroute_suggestions(settings: Any) -> None:
    vessels = [
        {
            "vessel_id": "V1",
            "name": "MV Giant",
            "eta": "2026-10-01 08:00",
            "size_teu": "3000",
            "cargo_type": "general",
            "priority": "1",
        }
    ]
    berths = [
        {"berth_id": "B1", "capacity_teu": "1000", "crane_count": "2", "avg_dwell_hours": "6.0"}
    ]
    plan = generate_ops_plan(vessels, berths)

    assert plan["berth_assignments"] == []
    assert plan["unassigned_count"] == 1
    assert plan["reroute_suggestions"][0]["vessel_id"] == "V1"


def test_a_failing_engine_degrades_to_a_warning(
    settings: Any, monkeypatch: pytest.MonkeyPatch, vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise PlanningError("forecast engine offline")

    monkeypatch.setattr(planner, "predict_congestion", boom)
    plan = generate_ops_plan(vessel_rows, berth_rows)

    assert plan["congestion_forecast"] == []
    assert plan["warnings"] == ["Congestion forecast unavailable: forecast engine offline"]
    # The rest of the plan is still produced.
    assert len(plan["berth_assignments"]) == 3


def test_unexpected_engine_error_does_not_leak_details(
    settings: Any, monkeypatch: pytest.MonkeyPatch, vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("connection string postgres://user:secret@host/db")

    monkeypatch.setattr(planner, "assign_berths", boom)
    plan = generate_ops_plan(vessel_rows, berth_rows)

    assert plan["warnings"] == ["Berth assignment unavailable due to an internal error."]
    assert "secret" not in str(plan)


def test_missing_berths_produce_warnings_not_an_exception(
    settings: Any, vessel_rows: list[Row]
) -> None:
    plan = generate_ops_plan(vessel_rows, [])
    assert len(plan["warnings"]) == 2
    assert plan["unassigned_count"] == 3


def test_50_record_datasets_plan_generation() -> None:
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    vessels_path = fixtures_dir / "test_vessels_50.csv"
    berths_path = fixtures_dir / "test_berths_50.csv"
    if vessels_path.exists() and berths_path.exists():
        from portpulse.csv_io import read_csv_file

        vessels = read_csv_file(vessels_path)
        berths = read_csv_file(berths_path)
        start_now = datetime(2026, 9, 20, 0, 0)
        plan = generate_ops_plan(vessels, berths, now=start_now)
        assert len(plan["berth_assignments"]) + plan["unassigned_count"] == 50
        OpsPlan.model_validate(plan)
