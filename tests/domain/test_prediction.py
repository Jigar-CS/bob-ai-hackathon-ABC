"""Congestion prediction."""

from __future__ import annotations

from datetime import datetime

import pytest

from portpulse.domain.prediction import predict_congestion
from portpulse.errors import PlanningError

Row = dict[str, str]

# A fixed reference point that makes all "2026-10-01/02" test ETAs fall
# within the 72-hour planning horizon regardless of when the suite runs.
_NOW = datetime(2026, 10, 1, 8, 0)


def test_windows_are_bucketed_by_rolling_24h_from_now(
    vessel_rows: list[Row], berth_rows: list[Row]
) -> None:
    windows = predict_congestion(vessel_rows, berth_rows, now=_NOW)

    assert [w["day"] for w in windows] == [1, 2, 3]
    assert len(windows) == 3
    assert windows[0]["vessel_count"] == 2
    assert windows[0]["incoming_teu"] == 12_000
    assert windows[0]["total_capacity_teu"] == 28_000
    assert windows[0]["window_start"] == "2026-10-01 08:00"
    assert windows[0]["window_end"] == "2026-10-02 08:00"


@pytest.mark.parametrize(
    ("incoming", "expected"),
    [(1_000, "LOW"), (7_000, "MEDIUM"), (9_500, "HIGH")],
)
def test_risk_level_thresholds(incoming: int, expected: str) -> None:
    vessels = [{"vessel_id": "V1", "eta": "2026-10-01 08:00", "size_teu": str(incoming)}]
    berths = [{"berth_id": "B1", "capacity_teu": "10000"}]
    assert predict_congestion(vessels, berths, now=_NOW)[0]["risk_level"] == expected


def test_thresholds_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTPULSE_ML_ENABLED", "true")
    from portpulse.config import reset_settings_cache

    reset_settings_cache()

    vessels = [{"vessel_id": "V1", "eta": "2026-10-01 08:00", "size_teu": "5000"}]
    berths = [{"berth_id": "B1", "capacity_teu": "10000"}]
    windows = predict_congestion(
        vessels, berths, high_risk_ratio=0.4, medium_risk_ratio=0.2, now=_NOW
    )
    assert windows[0]["risk_level"] == "HIGH"


def test_rows_with_unusable_values_are_skipped(berth_rows: list[Row]) -> None:
    vessels = [
        {"vessel_id": "V1", "eta": "2026-10-01 08:00", "size_teu": "5000"},
        {"vessel_id": "V2", "eta": "not-a-date", "size_teu": "5000"},
        {"vessel_id": "V3", "eta": "2026-10-01 09:00", "size_teu": "abc"},
    ]
    windows = predict_congestion(vessels, berth_rows, now=_NOW)
    assert len(windows) == 3
    assert windows[0]["incoming_teu"] == 5_000


def test_vessels_beyond_the_horizon_are_excluded(berth_rows: list[Row]) -> None:
    vessels = [
        {"vessel_id": "V1", "eta": "2026-10-01 08:00", "size_teu": "1000"},
        {"vessel_id": "V2", "eta": "2026-10-09 08:00", "size_teu": "9999"},
    ]
    windows = predict_congestion(vessels, berth_rows, now=_NOW)
    assert len(windows) == 3
    assert windows[0]["incoming_teu"] == 1_000


def test_always_returns_exact_horizon_days_windows() -> None:
    vessels = [{"vessel_id": "V1", "eta": "2026-10-01 08:00", "size_teu": "1000"}]
    berths = [{"berth_id": "B1", "capacity_teu": "10000"}]
    windows = predict_congestion(vessels, berths, horizon_days=3, now=_NOW)
    assert len(windows) == 3
    assert [w["day"] for w in windows] == [1, 2, 3]
    assert windows[0]["vessel_count"] == 1
    assert windows[1]["vessel_count"] == 0
    assert windows[2]["vessel_count"] == 0


@pytest.mark.parametrize(
    ("vessels", "berths", "message"),
    [
        ([], [{"berth_id": "B1", "capacity_teu": "1000"}], "At least one vessel"),
        ([{"eta": "2026-10-01 08:00", "size_teu": "10"}], [], "At least one berth"),
        (
            [{"eta": "2026-10-01 08:00", "size_teu": "10"}],
            [{"berth_id": "B1", "capacity_teu": "0"}],
            "capacity is zero",
        ),
        (
            [{"eta": "bad", "size_teu": "10"}],
            [{"berth_id": "B1", "capacity_teu": "1000"}],
            "usable ETA",
        ),
    ],
)
def test_unusable_input_raises_planning_error(
    vessels: list[Row], berths: list[Row], message: str
) -> None:
    with pytest.raises(PlanningError, match=message):
        predict_congestion(vessels, berths)
