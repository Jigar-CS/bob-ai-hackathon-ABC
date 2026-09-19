"""Unified ML predictor for PortPulse.

Loads all trained models once and exposes one function per prediction task.
Every function returns None on any failure (missing file, bad input, load
error) so callers can fall back to the existing rule-based/heuristic logic
without ever raising — matching the project's existing resilient-fallback
pattern used for watsonx.ai.

Models are called with named Pandas DataFrames so that sklearn does not emit
feature_names warnings (models were trained with DataFrame columns).

This enhanced version supports:
- 9 production ML models (risk, wait, allocation, cascade, weather, demurrage, crane, anomaly)
- Weather-aware predictions with real-time API integration
- Temporal features (hour, day, month, seasonality)
- Feature engineering pipeline

Optional: logs each risk/wait prediction to the `prediction_log` MySQL table
via db.py, if the DB is reachable. Logging failures never affect the caller.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_MODEL_DIR = Path(__file__).parent

# Model instances
_risk_model = None
_risk_encoder = None
_wait_model = None
_demurrage_model = None
_crane_model = None
_anomaly_model = None
_allocation_model = None
_cascade_model = None
_weather_delay_model = None
_feature_columns = None
_load_attempted = False


def _load() -> None:
    global _risk_model, _risk_encoder, _wait_model
    global _demurrage_model, _crane_model, _anomaly_model
    global _allocation_model, _cascade_model, _weather_delay_model
    global _feature_columns, _load_attempted
    
    if _load_attempted:
        return
    _load_attempted = True
    
    try:
        import joblib

        # Load original 6 models (backward compatibility)
        risk_path = _MODEL_DIR / "risk_model.pkl"
        if risk_path.exists():
            _risk_model = joblib.load(risk_path)
        
        encoder_path = _MODEL_DIR / "risk_label_encoder.pkl"
        if encoder_path.exists():
            _risk_encoder = joblib.load(encoder_path)
        
        wait_path = _MODEL_DIR / "wait_model.pkl"
        if wait_path.exists():
            _wait_model = joblib.load(wait_path)
        
        dem_path = _MODEL_DIR / "demurrage_model.pkl"
        if dem_path.exists():
            _demurrage_model = joblib.load(dem_path)
        
        crane_path = _MODEL_DIR / "crane_productivity_model.pkl"
        if crane_path.exists():
            _crane_model = joblib.load(crane_path)
        
        anom_path = _MODEL_DIR / "anomaly_model.pkl"
        if anom_path.exists():
            _anomaly_model = joblib.load(anom_path)
        
        # Load enhanced models (if available)
        alloc_path = _MODEL_DIR / "berth_allocation_model.pkl"
        if alloc_path.exists():
            _allocation_model = joblib.load(alloc_path)
        
        cascade_path = _MODEL_DIR / "delay_cascade_model.pkl"
        if cascade_path.exists():
            _cascade_model = joblib.load(cascade_path)
        
        weather_path = _MODEL_DIR / "weather_delay_model.pkl"
        if weather_path.exists():
            _weather_delay_model = joblib.load(weather_path)
        
        # Load feature columns for enhanced models
        feat_path = _MODEL_DIR / "feature_columns.pkl"
        if feat_path.exists():
            _feature_columns = joblib.load(feat_path)
        
        loaded_count = sum([
            _risk_model is not None,
            _wait_model is not None,
            _demurrage_model is not None,
            _crane_model is not None,
            _anomaly_model is not None,
            _allocation_model is not None,
            _cascade_model is not None,
            _weather_delay_model is not None,
        ])
        
        logger.info("Loaded %d ML models from %s", loaded_count, _MODEL_DIR)
        
    except Exception as err:
        logger.warning("Could not load one or more ML models: %s", err)


def _df(columns: list[str], values: list[object]):
    """Wrap a single prediction row in a named DataFrame to suppress sklearn warnings."""
    import pandas as pd
    return pd.DataFrame([values], columns=columns)


def _get_features(feature_set_name: str, default_columns: list[str]) -> list[str]:
    """Get feature columns for a model, with fallback to defaults."""
    if _feature_columns is None:
        return default_columns
    return _feature_columns.get(feature_set_name, default_columns)


# ---------------------------------------------------------------------------
# Model availability checks
# ---------------------------------------------------------------------------

def is_ml_enabled() -> bool:
    """Check if ML models are available and loaded."""
    _load()
    return _risk_model is not None or _wait_model is not None


def get_available_models() -> list[str]:
    """Get list of available model names."""
    _load()
    models = []
    if _risk_model is not None:
        models.append("risk_model")
    if _wait_model is not None:
        models.append("wait_model")
    if _demurrage_model is not None:
        models.append("demurrage_model")
    if _crane_model is not None:
        models.append("crane_productivity_model")
    if _anomaly_model is not None:
        models.append("anomaly_model")
    if _allocation_model is not None:
        models.append("berth_allocation_model")
    if _cascade_model is not None:
        models.append("delay_cascade_model")
    if _weather_delay_model is not None:
        models.append("weather_delay_model")
    return models


# ---------------------------------------------------------------------------
# Congestion risk classifier
# ---------------------------------------------------------------------------
def predict_risk(features: dict[str, Any]) -> str | None:
    """Predict congestion risk level for a 24-h window.

    Args:
        features: dict with keys ``vessel_count``, ``incoming_teu``,
            ``total_capacity_teu``, ``day_index``, ``utilization_ratio``.

    Returns:
        ``"LOW"``, ``"MEDIUM"``, or ``"HIGH"``; ``None`` on any failure.
    """
    _load()
    if _risk_model is None or _risk_encoder is None:
        return None
    try:
        X = _df(
            ["vessel_count", "incoming_teu", "total_capacity_teu", "day_index", "utilization_ratio"],
            [
                features["vessel_count"],
                features["incoming_teu"],
                features["total_capacity_teu"],
                features["day_index"],
                features["utilization_ratio"],
            ],
        )
        pred = _risk_model.predict(X)
        return str(_risk_encoder.inverse_transform(pred)[0])
    except Exception as err:
        logger.warning("ML risk prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Vessel wait-time regressor
# ---------------------------------------------------------------------------
def predict_wait(features: dict[str, Any]) -> float | None:
    """Predict queue wait hours for a vessel at a given berth.

    Args:
        features: dict with keys ``size_teu``, ``priority``, ``crane_count``,
            ``berth_capacity_teu``, ``n_berths``, ``n_vessels``.

    Returns:
        Predicted wait hours (float, ≥ 0); ``None`` on any failure.
    """
    _load()
    if _wait_model is None:
        return None
    try:
        X = _df(
            ["size_teu", "priority", "crane_count", "berth_capacity_teu", "n_berths", "n_vessels"],
            [
                features["size_teu"],
                features["priority"],
                features["crane_count"],
                features["berth_capacity_teu"],
                features["n_berths"],
                features["n_vessels"],
            ],
        )
        return max(0.0, float(_wait_model.predict(X)[0]))
    except Exception as err:
        logger.warning("ML wait prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Demurrage cost regressor
# ---------------------------------------------------------------------------
def predict_demurrage_cost(features: dict[str, Any]) -> float | None:
    """Predict demurrage cost in USD for a vessel assignment.

    Args:
        features: dict with keys ``wait_hours``, ``priority``, ``size_teu``,
            ``cargo_type_hazmat`` (0 or 1).

    Returns:
        Predicted demurrage USD (float, ≥ 0); ``None`` on any failure.
    """
    _load()
    if _demurrage_model is None:
        return None
    try:
        X = _df(
            ["wait_hours", "priority", "size_teu", "cargo_type_hazmat"],
            [
                features["wait_hours"],
                features["priority"],
                features["size_teu"],
                features["cargo_type_hazmat"],
            ],
        )
        return max(0.0, float(_demurrage_model.predict(X)[0]))
    except Exception as err:
        logger.warning("Demurrage prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Crane productivity regressor
# ---------------------------------------------------------------------------
def predict_crane_productivity(features: dict[str, Any]) -> float | None:
    """Predict crane throughput in moves per hour.

    Args:
        features: dict with keys ``crane_count``, ``size_teu``, ``priority``,
            ``berth_capacity_teu``.

    Returns:
        Predicted moves/hour (float, > 0); ``None`` on any failure.
    """
    _load()
    if _crane_model is None:
        return None
    try:
        X = _df(
            ["crane_count", "size_teu", "priority", "berth_capacity_teu"],
            [
                features["crane_count"],
                features["size_teu"],
                features["priority"],
                features["berth_capacity_teu"],
            ],
        )
        return max(1.0, float(_crane_model.predict(X)[0]))
    except Exception as err:
        logger.warning("Crane productivity prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Anomaly detector
# ---------------------------------------------------------------------------
_logged_anomaly_error = False


def is_anomalous(features: dict[str, Any]) -> bool | None:
    """Detect whether a vessel's dwell/wait pattern is anomalous.

    Args:
        features: dict with keys ``size_teu``, ``effective_dwell_hours``,
            ``wait_hours``, ``crane_count``, ``priority``.

    Returns:
        ``True`` if flagged as anomaly, ``False`` if normal; ``None`` on failure.
    """
    global _logged_anomaly_error
    _load()
    if _anomaly_model is None:
        return None
    try:
        X = _df(
            ["size_teu", "effective_dwell_hours", "wait_hours", "crane_count", "priority"],
            [
                features["size_teu"],
                features["effective_dwell_hours"],
                features["wait_hours"],
                features["crane_count"],
                features["priority"],
            ],
        )
        pred = _anomaly_model.predict(X)[0]  # -1 anomaly, 1 normal
        return bool(pred == -1)
    except Exception as err:
        if not _logged_anomaly_error:
            logger.error("Anomaly prediction failed: %s", err)
            _logged_anomaly_error = True
        return None


# ---------------------------------------------------------------------------
# Optional: log a risk/wait prediction row to MySQL (prediction_log table)
# ---------------------------------------------------------------------------
def log_prediction(
    vessel_id: str,
    window_day: int,
    vessel_count: int,
    incoming_teu: int,
    total_capacity_teu: int,
    utilization_ratio: float,
    predicted_risk_level: str | None,
    predicted_wait_hours: float | None,
    model_version: str = "v2",
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    origin_port: str | None = None,
    dest_lat: float | None = None,
    dest_lon: float | None = None,
    dest_port: str | None = None,
    weather_delay_hours: float | None = None,
    weather_severity: str | None = None,
    predicted_demurrage_cost_usd: float | None = None,
    predicted_moves_per_hour: float | None = None,
    is_anomalous: bool | None = None,
    ml_allocation_used: bool | None = None,
) -> None:
    """Best-effort insert into prediction_log. Never raises."""
    try:
        from portpulse.db import PredictionLog, SessionLocal

        db = SessionLocal()
        try:
            entry = PredictionLog(
                created_at=datetime.now(UTC),
                vessel_id=vessel_id,
                window_day=window_day,
                vessel_count=vessel_count,
                incoming_teu=incoming_teu,
                total_capacity_teu=total_capacity_teu,
                utilization_ratio=utilization_ratio,
                predicted_risk_level=predicted_risk_level,
                predicted_wait_hours=predicted_wait_hours,
                model_version=model_version,
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                origin_port=origin_port,
                dest_lat=dest_lat,
                dest_lon=dest_lon,
                dest_port=dest_port,
                weather_delay_hours=weather_delay_hours,
                weather_severity=weather_severity,
                predicted_demurrage_cost_usd=predicted_demurrage_cost_usd,
                predicted_moves_per_hour=predicted_moves_per_hour,
                is_anomalous=1 if is_anomalous is True else (0 if is_anomalous is False else None),
                ml_allocation_used=1 if ml_allocation_used is True else (0 if ml_allocation_used is False else None),
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
    except Exception as err:
        logger.warning("Could not log prediction to DB: %s", err)


# ---------------------------------------------------------------------------
# Enhanced: Delay Cascade Prediction
# ---------------------------------------------------------------------------
def predict_cascade_delay(features: dict[str, Any]) -> float | None:
    """Predict cascading delay hours from an initial disruption.
    
    Args:
        features: dict with keys ``initial_wait_hours``, ``n_vessels_queue``,
            ``n_berths``, ``avg_vessel_size``, ``weather_severity``,
            ``priority_avg``, ``hour_of_day``, ``utilization_ratio``.
    
    Returns:
        Predicted cascade delay hours (float, ≥ 0); ``None`` on failure.
    """
    _load()
    if _cascade_model is None:
        return None
    try:
        columns = _get_features('cascade_features', [
            'initial_wait_hours', 'n_vessels_queue', 'n_berths',
            'avg_vessel_size', 'weather_severity', 'priority_avg',
            'hour_of_day', 'utilization_ratio'
        ])
        
        X = _df(columns, [
            features.get('initial_wait_hours', 0),
            features.get('n_vessels_queue', 0),
            features.get('n_berths', 5),
            features.get('avg_vessel_size', 10000),
            features.get('weather_severity', 0),
            features.get('priority_avg', 2.5),
            features.get('hour_of_day', 12),
            features.get('utilization_ratio', 0.5),
        ])
        
        return max(0.0, float(_cascade_model.predict(X)[0]))
    except Exception as err:
        logger.warning("Cascade delay prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Enhanced: Weather Delay Prediction
# ---------------------------------------------------------------------------
def predict_weather_delay(features: dict[str, Any]) -> float | None:
    """Predict weather-induced delay hours.
    
    Args:
        features: dict with keys ``wave_height_m``, ``wind_speed_kt``,
            ``visibility_km``, ``storm_probability``, ``precipitation_mm``,
            ``weather_severity``, ``distance_km``, ``month``, ``hour_of_day``,
            ``vessel_size_teu``.
    
    Returns:
        Predicted delay hours (float, ≥ 0); ``None`` on failure.
    """
    _load()
    if _weather_delay_model is None:
        return None
    try:
        columns = _get_features('weather_delay_features', [
            'wave_height_m', 'wind_speed_kt', 'visibility_km',
            'storm_probability', 'precipitation_mm', 'weather_severity',
            'distance_km', 'month', 'hour_of_day', 'vessel_size_teu'
        ])
        
        now = datetime.now()
        
        X = _df(columns, [
            features.get('wave_height_m', 0),
            features.get('wind_speed_kt', 0),
            features.get('visibility_km', 10),
            features.get('storm_probability', 0),
            features.get('precipitation_mm', 0),
            features.get('weather_severity', 0),
            features.get('distance_km', 1000),
            features.get('month', now.month),
            features.get('hour_of_day', now.hour),
            features.get('vessel_size_teu', 10000),
        ])
        
        return max(0.0, float(_weather_delay_model.predict(X)[0]))
    except Exception as err:
        logger.warning("Weather delay prediction failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Enhanced: Berth Allocation Scoring
# ---------------------------------------------------------------------------
def predict_allocation_score(features: dict[str, Any]) -> float | None:
    """Score a berth allocation (0-100, higher = better).
    
    Args:
        features: dict with keys ``vessel_size_teu``, ``vessel_priority``,
            ``berth_capacity_teu``, ``berth_crane_count``,
            ``berth_utilization_pct``, ``wave_height_m``, ``wind_speed_kt``,
            ``weather_severity``, ``hour_of_day``, ``n_vessels_queue``,
            ``capacity_fit_ratio``.
    
    Returns:
        Allocation score (float, 0-100); ``None`` on failure.
    """
    _load()
    if _allocation_model is None:
        return None
    try:
        columns = _get_features('allocation_features', [
            'vessel_size_teu', 'vessel_priority', 'berth_capacity_teu',
            'berth_crane_count', 'berth_utilization_pct', 'wave_height_m',
            'wind_speed_kt', 'weather_severity', 'hour_of_day',
            'n_vessels_queue', 'capacity_fit_ratio'
        ])
        
        vessel_size = features.get('vessel_size_teu', 10000)
        berth_capacity = features.get('berth_capacity_teu', 15000)
        capacity_fit = berth_capacity / max(vessel_size, 1)
        
        X = _df(columns, [
            vessel_size,
            features.get('vessel_priority', 2),
            berth_capacity,
            features.get('berth_crane_count', 3),
            features.get('berth_utilization_pct', 60),
            features.get('wave_height_m', 0),
            features.get('wind_speed_kt', 0),
            features.get('weather_severity', 0),
            features.get('hour_of_day', datetime.now().hour),
            features.get('n_vessels_queue', 10),
            features.get('capacity_fit_ratio', capacity_fit),
        ])
        
        score = float(_allocation_model.predict(X)[0])
        return max(0.0, min(100.0, score))
    except Exception as err:
        logger.warning("Allocation scoring failed: %s", err)
        return None


# ---------------------------------------------------------------------------
# Utility: Reload models
# ---------------------------------------------------------------------------
def reload_models() -> bool:
    """Force reload of all models from disk."""
    global _load_attempted
    _load_attempted = False
    _load()
    return is_ml_enabled()
