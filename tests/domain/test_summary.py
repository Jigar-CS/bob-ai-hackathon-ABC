"""Unit tests for the ops summary domain module."""

from __future__ import annotations

from unittest.mock import MagicMock

from portpulse.domain.summary import generate_ops_summary
from portpulse.integrations.watsonx import WatsonxError


def test_template_summary_fallback_with_high_risk_and_reroutes() -> None:
    plan = {
        "congestion_forecast": [
            {"day": 1, "risk_level": "HIGH", "vessel_count": 5},
            {"day": 2, "risk_level": "LOW", "vessel_count": 2},
        ],
        "berth_assignments": [
            {"vessel_id": "V1", "priority": "1"},
            {"vessel_id": "V2", "priority": "2"},
        ],
        "unassigned_count": 2,
        "reroute_suggestions": [{"vessel_name": "MV Alpha", "alternatives": [{"port": "Oakland"}]}],
    }

    res = generate_ops_summary(plan)
    assert res["ai_generated"] is False
    summary = str(res["summary"])
    assert "Day 1 is at HIGH congestion risk." in summary
    assert "2 vessels could not be berthed and are recommended for rerouting." in summary
    assert "2 vessels assigned across berths." in summary


def test_template_summary_fallback_no_high_risk_or_reroutes() -> None:
    plan = {
        "congestion_forecast": [
            {"day": 1, "risk_level": "LOW", "vessel_count": 1},
        ],
        "berth_assignments": [
            {"vessel_id": "V1", "priority": "1"},
        ],
        "unassigned_count": 0,
        "reroute_suggestions": [],
    }

    res = generate_ops_summary(plan)
    assert res["ai_generated"] is False
    summary = str(res["summary"])
    assert "No HIGH-risk congestion windows in the current horizon." in summary
    assert "All vessels have been assigned to berths." in summary


def test_generate_ops_summary_uses_watsonx_client() -> None:
    plan = {
        "congestion_forecast": [{"day": 1, "risk_level": "HIGH", "vessel_count": 5}],
        "berth_assignments": [{"vessel_id": "V1", "priority": "1"}],
        "unassigned_count": 1,
        "reroute_suggestions": [
            {"vessel_name": "MV Titan", "alternatives": [{"port": "Ensenada"}]}
        ],
    }

    mock_client = MagicMock()
    mock_client.enabled = True
    mock_client.generate_text.return_value = "Custom AI summary for supervisor."

    res = generate_ops_summary(plan, client=mock_client)
    assert res["ai_generated"] is True
    assert res["summary"] == "Custom AI summary for supervisor."


def test_generate_ops_summary_falls_back_on_watsonx_error() -> None:
    plan = {
        "congestion_forecast": [],
        "berth_assignments": [],
        "unassigned_count": 0,
        "reroute_suggestions": [],
    }

    mock_client = MagicMock()
    mock_client.enabled = True
    mock_client.generate_text.side_effect = WatsonxError("Service down")

    res = generate_ops_summary(plan, client=mock_client)
    assert res["ai_generated"] is False
    assert "No HIGH-risk congestion windows" in str(res["summary"])
