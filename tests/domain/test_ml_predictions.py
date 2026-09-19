"""Unit tests for ML predictions and graceful fallback."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from portpulse.config import reset_settings_cache
from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.planner import generate_ops_plan
from portpulse.ml import predictor


def test_ml_disabled_by_default_returns_none_fields():
    os.environ["PORTPULSE_ML_ENABLED"] = "false"
    reset_settings_cache()

    plan = generate_ops_plan(load_vessels(), load_berths())
    assignments = plan.get("berth_assignments", [])

    assert len(assignments) > 0
    for a in assignments:
        assert a.get("predicted_wait_hours") is None
        assert a.get("predicted_demurrage_cost_usd") is None
        assert a.get("predicted_moves_per_hour") is None
        assert a.get("is_anomalous") is None


def test_ml_enabled_populates_all_model_outputs():
    os.environ["PORTPULSE_ML_ENABLED"] = "true"
    reset_settings_cache()

    plan = generate_ops_plan(load_vessels(), load_berths())
    assignments = plan.get("berth_assignments", [])
    forecast = plan.get("congestion_forecast", [])

    assert len(forecast) > 0
    assert forecast[0]["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    assert len(assignments) > 0
    for a in assignments:
        assert a.get("predicted_wait_hours") is not None
        assert a.get("predicted_demurrage_cost_usd") is not None
        assert a.get("predicted_moves_per_hour") is not None
        assert isinstance(a.get("is_anomalous"), bool)

    # Clean up env
    os.environ["PORTPULSE_ML_ENABLED"] = "false"
    reset_settings_cache()


def test_missing_or_corrupted_models_fallback_gracefully():
    # Reset all model state globals
    predictor._load_attempted = False
    predictor._risk_model = None
    predictor._risk_encoder = None
    predictor._wait_model = None
    predictor._demurrage_model = None
    predictor._crane_model = None
    predictor._anomaly_model = None

    # Simulate missing model files by patching _MODEL_DIR to a non-existent path
    with patch("portpulse.ml.predictor._MODEL_DIR", Path("/nonexistent/directory")):
        risk = predictor.predict_risk(
            {
                "vessel_count": 5,
                "incoming_teu": 20000,
                "total_capacity_teu": 30000,
                "day_index": 1,
                "utilization_ratio": 0.67,
            }
        )
        wait = predictor.predict_wait(
            {
                "size_teu": 6000,
                "priority": 1,
                "crane_count": 4,
                "berth_capacity_teu": 16000,
                "n_berths": 6,
                "n_vessels": 20,
            }
        )
        demurrage = predictor.predict_demurrage_cost(
            {
                "wait_hours": 2.0,
                "priority": 1,
                "size_teu": 6000,
                "cargo_type_hazmat": 0,
            }
        )
        crane = predictor.predict_crane_productivity(
            {
                "crane_count": 4,
                "size_teu": 6000,
                "priority": 1,
                "berth_capacity_teu": 16000,
            }
        )
        anomaly = predictor.is_anomalous(
            {
                "size_teu": 6000,
                "effective_dwell_hours": 24.0,
                "wait_hours": 2.0,
                "crane_count": 4,
                "priority": 1,
            }
        )

        assert risk is None
        assert wait is None
        assert demurrage is None
        assert crane is None
        assert anomaly is None

    # Reset load state for subsequent tests
    predictor._load_attempted = False
    predictor._load()
