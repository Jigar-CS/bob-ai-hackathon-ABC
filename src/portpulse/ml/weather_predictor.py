"""
ML-Based Weather Delay Prediction Module

Combines real-time weather API data with trained ML models to predict:
- Weather-induced vessel delays
- Route-specific weather impacts
- Dynamic ETA adjustments based on marine conditions

Features:
- Integrates Open-Meteo Marine API for real-time data
- Uses trained ML models for delay prediction
- Considers multiple waypoints along vessel routes
- Provides confidence scores for predictions
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import requests

from portpulse.constants import ETA_FORMAT
from portpulse.csv_io import Row, parse_eta
from portpulse.domain.port_directory import calculate_sea_distance

logger = logging.getLogger(__name__)

# API endpoints
_MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
_WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Weather severity thresholds
SEVERE_WAVE_M = 5.0
SEVERE_WIND_KT = 50.0
MODERATE_WAVE_M = 3.0
MODERATE_WIND_KT = 35.0
MINOR_WAVE_M = 1.5
MINOR_WIND_KT = 25.0

LIGHT_WAVE_M = 1.5
LIGHT_WIND_KT = 15.0


class WeatherPredictor:
    """ML model for weather delay prediction based on wave height, wind speed, etc."""

    # Class-level shared model instances to prevent reloading on every call
    _shared_model = None
    _shared_feature_columns = None
    _shared_load_attempted = False

    def __init__(self) -> None:
        self._model = WeatherPredictor._shared_model
        self._feature_columns = WeatherPredictor._shared_feature_columns

    def _load_model(self) -> bool:
        """Load the weather delay ML model."""
        if WeatherPredictor._shared_load_attempted:
            self._model = WeatherPredictor._shared_model
            self._feature_columns = WeatherPredictor._shared_feature_columns
            return self._model is not None

        WeatherPredictor._shared_load_attempted = True

        try:
            from pathlib import Path

            import joblib

            model_dir = Path(__file__).parent
            model_path = model_dir / "weather_delay_model.pkl"
            if model_path.exists():
                WeatherPredictor._shared_model = joblib.load(model_path)
                self._model = WeatherPredictor._shared_model

            feature_cols_path = model_dir / "feature_columns.pkl"
            if feature_cols_path.exists():
                feature_columns = joblib.load(feature_cols_path)
                WeatherPredictor._shared_feature_columns = feature_columns.get(
                    "weather_delay_features", []
                )
                self._feature_columns = WeatherPredictor._shared_feature_columns

            if self._model is not None:
                logger.info("Weather delay ML model loaded successfully")
                return True
        except Exception as err:
            logger.debug("Could not load weather delay model: %s", err)

        return False

    def predict_delay(
        self,
        wave_height_m: float,
        wind_speed_kt: float,
        visibility_km: float = 10.0,
        storm_probability: float = 0.0,
        precipitation_mm: float = 0.0,
        distance_km: float = 1000.0,
        vessel_size_teu: int = 10000,
        month: int | None = None,
        hour_of_day: int | None = None,
    ) -> dict[str, Any]:
        """
        Predict weather-induced delay using ML model.

        Returns dict with:
            - delay_hours: Predicted delay in hours
            - severity: Weather severity level (none/minor/moderate/severe)
            - confidence: Prediction confidence (0-1)
            - factors: Key contributing factors
        """
        # Determine severity based on conditions
        severity = self._classify_severity(wave_height_m, wind_speed_kt)

        # Default hour and month if not provided
        if hour_of_day is None:
            hour_of_day = datetime.now().hour
        if month is None:
            month = datetime.now().month

        # Try ML prediction first
        if self._load_model() and self._model is not None:
            try:
                features = pd.DataFrame(
                    [
                        {
                            "wave_height_m": wave_height_m,
                            "wind_speed_kt": wind_speed_kt,
                            "visibility_km": visibility_km,
                            "storm_probability": storm_probability,
                            "precipitation_mm": precipitation_mm,
                            "weather_severity": self._severity_to_int(severity),
                            "distance_km": distance_km,
                            "month": month,
                            "hour_of_day": hour_of_day,
                            "vessel_size_teu": vessel_size_teu,
                        }
                    ]
                )

                # Ensure correct feature order
                if self._feature_columns:
                    features = features[self._feature_columns]

                predicted_delay = max(0.0, float(self._model.predict(features)[0]))

                # Calculate confidence based on feature values
                confidence = self._calculate_confidence(
                    wave_height_m, wind_speed_kt, storm_probability
                )

                return {
                    "delay_hours": round(predicted_delay, 2),
                    "severity": severity,
                    "confidence": round(confidence, 3),
                    "factors": self._identify_factors(
                        wave_height_m,
                        wind_speed_kt,
                        visibility_km,
                        storm_probability,
                        precipitation_mm,
                    ),
                    "model_used": "ml",
                }
            except Exception as err:
                logger.warning("ML weather prediction failed: %s", err)

        # Fallback to rule-based prediction
        delay_hours = self._rule_based_delay(
            wave_height_m, wind_speed_kt, storm_probability, distance_km
        )

        return {
            "delay_hours": round(delay_hours, 2),
            "severity": severity,
            "confidence": 0.5,  # Lower confidence for rule-based
            "factors": self._identify_factors(
                wave_height_m, wind_speed_kt, visibility_km, storm_probability, precipitation_mm
            ),
            "model_used": "rule_based",
        }

    def _classify_severity(self, wave_height_m: float, wind_speed_kt: float) -> str:
        """Classify weather severity based on conditions."""
        if wave_height_m >= SEVERE_WAVE_M or wind_speed_kt >= SEVERE_WIND_KT:
            return "severe"
        elif wave_height_m >= MODERATE_WAVE_M or wind_speed_kt >= MODERATE_WIND_KT:
            return "moderate"
        elif (
            wave_height_m >= MINOR_WAVE_M
            or wind_speed_kt >= MINOR_WIND_KT
            or wave_height_m >= 1.2
            or wind_speed_kt >= 18.0
        ):
            return "minor"
        return "none"

    def _severity_to_int(self, severity: str) -> int:
        """Convert severity string to integer."""
        return {"none": 0, "minor": 1, "moderate": 2, "severe": 3}.get(severity, 0)

    def _calculate_confidence(
        self, wave_height_m: float, wind_speed_kt: float, storm_prob: float
    ) -> float:
        """Calculate prediction confidence based on conditions."""
        # Higher confidence when conditions are more extreme (clearer signal)
        wave_conf = min(1.0, wave_height_m / 8.0)
        wind_conf = min(1.0, wind_speed_kt / 60.0)
        storm_conf = storm_prob

        # Average confidence
        base_confidence = 0.6 + 0.4 * float(np.mean([wave_conf, wind_conf, storm_conf]))
        return float(min(0.95, base_confidence))

    def _identify_factors(
        self,
        wave_height_m: float,
        wind_speed_kt: float,
        visibility_km: float,
        storm_probability: float,
        precipitation_mm: float,
    ) -> list[str]:
        """Identify key contributing factors to the delay."""
        factors = []

        if wave_height_m >= SEVERE_WAVE_M:
            factors.append(f"Extreme wave height ({wave_height_m:.1f}m)")
        elif wave_height_m >= MODERATE_WAVE_M:
            factors.append(f"High wave height ({wave_height_m:.1f}m)")
        elif wave_height_m >= MINOR_WAVE_M:
            factors.append(f"Moderate wave height ({wave_height_m:.1f}m)")

        if wind_speed_kt >= SEVERE_WIND_KT:
            factors.append(f"Storm-force winds ({wind_speed_kt:.0f}kt)")
        elif wind_speed_kt >= MODERATE_WIND_KT:
            factors.append(f"Strong winds ({wind_speed_kt:.0f}kt)")
        elif wind_speed_kt >= MINOR_WIND_KT:
            factors.append(f"Moderate winds ({wind_speed_kt:.0f}kt)")

        if storm_probability > 0.7:
            factors.append(f"High storm probability ({storm_probability:.0%})")
        elif storm_probability > 0.4:
            factors.append(f"Moderate storm risk ({storm_probability:.0%})")

        if visibility_km < 2:
            factors.append(f"Low visibility ({visibility_km:.1f}km)")

        if precipitation_mm > 20:
            factors.append(f"Heavy precipitation ({precipitation_mm:.0f}mm)")

        return factors if factors else ["Clear conditions"]

    def _rule_based_delay(
        self,
        wave_height_m: float,
        wind_speed_kt: float,
        storm_probability: float,
        distance_km: float,
    ) -> float:
        """Rule-based delay calculation (fallback when ML unavailable)."""
        # Base delay from wave height
        wave_delay = 0.0
        if wave_height_m >= SEVERE_WAVE_M:
            wave_delay = 8 + (wave_height_m - SEVERE_WAVE_M) * 2
        elif wave_height_m >= MODERATE_WAVE_M:
            wave_delay = 3 + (wave_height_m - MODERATE_WAVE_M) * 1.5
        elif wave_height_m >= MINOR_WAVE_M:
            wave_delay = 1.0 + (wave_height_m - MINOR_WAVE_M) * 1.0
        elif wave_height_m >= 1.2:
            wave_delay = 0.3 + (wave_height_m - 1.2) * 0.8

        # Wind delay contribution
        wind_delay = 0.0
        if wind_speed_kt >= SEVERE_WIND_KT:
            wind_delay = 6 + (wind_speed_kt - SEVERE_WIND_KT) * 0.1
        elif wind_speed_kt >= MODERATE_WIND_KT:
            wind_delay = 2 + (wind_speed_kt - MODERATE_WIND_KT) * 0.1
        elif wind_speed_kt >= MINOR_WIND_KT:
            wind_delay = 0.5 + (wind_speed_kt - MINOR_WIND_KT) * 0.05
        elif wind_speed_kt >= 18.0:
            wind_delay = 0.2 + (wind_speed_kt - 18.0) * 0.03

        # Storm probability multiplier
        storm_multiplier = 1.0 + storm_probability * 0.5

        # Distance factor (longer routes = more exposure)
        distance_factor = max(0.8, min(1.5, distance_km / 2000)) if distance_km > 0 else 1.0

        total_delay = (wave_delay + wind_delay) * storm_multiplier * distance_factor
        return max(0.0, total_delay)


def estimate_oceanic_conditions(lat: float, lon: float, eta: datetime) -> tuple[float, float]:
    """Estimate realistic marine wave height (m) and wind speed (kt) for ocean coordinates."""
    abs_lat = abs(lat)
    lat_factor = math.sin(math.radians(min(90.0, abs_lat * 1.5)))

    day_seed = eta.day if isinstance(eta, datetime) else 15
    hour_seed = eta.hour if isinstance(eta, datetime) else 12
    var1 = math.sin(lat * 0.35 + lon * 0.22 + day_seed * 0.5)
    var2 = math.cos(lat * 0.18 - lon * 0.41 + hour_seed * 0.7)

    wave_m = max(1.2, 1.8 + 2.5 * lat_factor + 1.2 * var1)
    wind_kt = max(15.0, 18.0 + 22.0 * lat_factor + 10.0 * var2)
    return round(wave_m, 2), round(wind_kt, 2)


def fetch_marine_weather(
    lat: float,
    lon: float,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """
    Fetch marine weather forecast from Open-Meteo API.

    Returns raw JSON data or empty dict on failure.
    """
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "hourly": "wave_height,wind_speed_10m",
        "wind_speed_unit": "ms",
        "forecast_days": 7,
        "timezone": "UTC",
    }

    try:
        # Try marine API first
        resp = requests.get(_MARINE_API_URL, params=params, timeout=timeout)  # type: ignore[arg-type]
        if resp.status_code == 200:
            data = resp.json()
            if "hourly" in data:
                return data
    except Exception:
        pass

    # Fallback to standard forecast API
    try:
        fallback_params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": "wind_speed_10m",
            "wind_speed_unit": "ms",
            "forecast_days": 7,
            "timezone": "UTC",
        }
        resp = requests.get(_WEATHER_API_URL, params=fallback_params, timeout=timeout)  # type: ignore[arg-type]
        resp.raise_for_status()
        return resp.json()
    except Exception as err:
        logger.warning("Weather API unavailable for (%.4f, %.4f): %s", lat, lon, err)
        return {}


def extract_weather_conditions(
    data: dict[str, Any],
    eta: datetime,
    window_hours: int = 24,
    lat: float = 0.0,
    lon: float = 0.0,
) -> tuple[float, float, float, float]:
    """
    Extract weather conditions from API data for a time window.
    Fallback to realistic ocean conditions if API data is out-of-range or missing.

    Returns: (max_wave_m, max_wind_kt, avg_wave_m, avg_wind_kt)
    """
    try:
        hourly = data.get("hourly", {})
        times: list[str] = hourly.get("time", [])
        waves: list[float | None] = hourly.get("wave_height", [])
        winds: list[float | None] = hourly.get("wind_speed_10m", [])

        window_end = eta
        window_start = eta - timedelta(hours=window_hours)

        wave_values: list[float] = []
        wind_values: list[float] = []

        for i, t_str in enumerate(times):
            try:
                t = datetime.fromisoformat(t_str)
            except ValueError:
                continue

            # Match window or if ETA is out-of-range, match by hour of day
            if (window_start <= t <= window_end) or (
                eta and abs(t.hour - eta.hour) <= 3 and not wave_values
            ):
                w = waves[i] if i < len(waves) else None
                v = winds[i] if i < len(winds) else None
                if w is not None and float(w) > 0:
                    wave_values.append(float(w))
                if v is not None and float(v) > 0:
                    wind_values.append(float(v) * 1.944)  # m/s to knots

        # If no wave/wind values found from API (e.g. out-of-range or ocean point), use ocean model
        if (
            not wave_values
            or not wind_values
            or (max(wave_values or [0]) == 0 and max(wind_values or [0]) == 0)
        ):
            est_wave, est_wind = estimate_oceanic_conditions(lat, lon, eta)
            return est_wave, est_wind, est_wave * 0.85, est_wind * 0.85

        max_w = max(wave_values) if wave_values else 0.0
        max_v = max(wind_values) if wind_values else 0.0

        # If wave height is missing from API but wind speed exists, estimate wave from wind & lat
        if max_w == 0.0 and max_v > 0.0:
            est_w, _ = estimate_oceanic_conditions(lat, lon, eta)
            max_w = est_w

        return (
            max_w,
            max_v,
            float(np.mean(wave_values)) if wave_values else max_w,
            float(np.mean(wind_values)) if wind_values else max_v,
        )
    except Exception as err:
        logger.debug("Could not extract weather conditions: %s", err)
        est_wave, est_wind = estimate_oceanic_conditions(lat, lon, eta)
        return est_wave, est_wind, est_wave * 0.85, est_wind * 0.85


def calculate_route_waypoints(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    n_waypoints: int = 5,
) -> list[tuple[float, float]]:
    """
    Calculate evenly spaced waypoints along a vessel route, handling antimeridian crossing.

    Returns list of (lat, lon) tuples.
    """
    waypoints = []
    o_lon = origin_lon
    d_lon = dest_lon

    delta_lon = d_lon - o_lon
    if delta_lon > 180:
        d_lon -= 360
    elif delta_lon < -180:
        d_lon += 360

    for step in range(1, n_waypoints + 1):
        frac = step / (n_waypoints + 1)
        lat = origin_lat + frac * (dest_lat - origin_lat)
        lon = o_lon + frac * (d_lon - o_lon)

        if lon > 180:
            lon -= 360
        elif lon < -180:
            lon += 360
        waypoints.append((round(lat, 4), round(lon, 4)))

    return waypoints


def predict_route_weather_delays(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    eta: datetime,
    vessel_size_teu: int = 10000,
    n_waypoints: int = 5,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """
    Predict weather delays along a vessel's entire route.

    Returns aggregated weather impact for the route.
    """
    predictor = WeatherPredictor()

    # Get waypoints
    waypoints = calculate_route_waypoints(origin_lat, origin_lon, dest_lat, dest_lon, n_waypoints)

    # Fetch weather at each waypoint
    waypoint_delays = []
    max_severity = "none"
    severity_order = {"none": 0, "minor": 1, "moderate": 2, "severe": 3}

    for lat, lon in waypoints:
        weather_data = fetch_marine_weather(lat, lon, timeout=timeout)
        max_wave, max_wind, _avg_wave, _avg_wind = extract_weather_conditions(
            weather_data, eta, lat=lat, lon=lon
        )

        # Predict delay for this waypoint
        result = predictor.predict_delay(
            wave_height_m=max_wave,
            wind_speed_kt=max_wind,
            distance_km=0,  # Per-waypoint, not total distance
            vessel_size_teu=vessel_size_teu,
        )

        waypoint_delays.append(
            {
                "lat": lat,
                "lon": lon,
                "delay_hours": result["delay_hours"],
                "severity": result["severity"],
                "max_wave_m": max_wave,
                "max_wind_kt": max_wind,
            }
        )

        # Track worst severity
        if severity_order.get(result["severity"], 0) > severity_order.get(max_severity, 0):
            max_severity = result["severity"]

    # Aggregate delays (peak delay + route corridor scale, capped at 24h)
    if waypoint_delays:
        delays = [w["delay_hours"] for w in waypoint_delays]
        max_d = max(delays)
        sum_d = sum(delays)
        total_delay = min(24.0, max_d + 0.15 * (sum_d - max_d))
        avg_confidence = np.mean(delays) / max(total_delay, 0.1)
    else:
        total_delay = 0.0
        avg_confidence = 0.5
        max_severity = "none"

    # Calculate route maritime sea distance in nmi and km
    dist_nmi, dist_km = calculate_sea_distance(origin_lat, origin_lon, dest_lat, dest_lon)

    return {
        "total_delay_hours": round(total_delay, 2),
        "max_severity": max_severity,
        "confidence": round(min(0.95, avg_confidence + 0.3), 3),
        "distance_nmi": dist_nmi,
        "distance_km": float(dist_km),
        "waypoint_count": len(waypoint_delays),
        "waypoint_details": waypoint_delays[:3],  # Top 3 for display
        "model_used": "ml" if predictor._model is not None else "rule_based",
    }


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    R = 6371  # Earth's radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def apply_ml_weather_delays(
    vessels: list[Row],
    port_lat: float,
    port_lon: float,
    timeout: float = 5.0,
    n_waypoints: int = 5,
) -> tuple[list[Row], list[dict[str, Any]]]:
    """
    Apply ML-predicted weather delays to vessel dataset.

    Uses ThreadPoolExecutor parallelization and coordinate caching for high performance.
    """
    from concurrent.futures import ThreadPoolExecutor

    from portpulse.config import get_settings

    if not vessels:
        return [], []

    try:
        settings = get_settings().app
        max_vessels = getattr(settings, "weather_max_vessels", 200)
        max_workers = getattr(settings, "weather_max_workers", 8)
    except Exception:
        max_vessels = 200
        max_workers = 8

    predictor = WeatherPredictor()
    vessels_to_process = vessels[:max_vessels]
    capped_vessels = vessels[max_vessels:]

    def process_vessel(vessel_row: Row) -> tuple[Row, dict[str, Any] | None]:
        vessel = dict(vessel_row)

        try:
            eta = parse_eta(vessel.get("eta"))
        except Exception:
            vessel["weather_delay_hours"] = 0.0
            vessel["weather_severity"] = "none"
            return vessel, None

        try:
            vessel_size = int(vessel.get("size_teu", 10000))
        except (TypeError, ValueError):
            vessel_size = 10000

        try:
            o_lat = float(vessel.get("origin_lat") or "")
            o_lon = float(vessel.get("origin_lon") or "")
            has_origin = True
        except (TypeError, ValueError):
            has_origin = False

        try:
            target_lat = float(
                port_lat if port_lat is not None else (vessel.get("dest_lat") or 18.95)
            )
            target_lon = float(
                port_lon if port_lon is not None else (vessel.get("dest_lon") or 72.95)
            )
        except (TypeError, ValueError):
            target_lat, target_lon = port_lat, port_lon

        if has_origin:
            result = predict_route_weather_delays(
                o_lat, o_lon, target_lat, target_lon, eta, vessel_size, n_waypoints, timeout
            )
            delay_hours = result["total_delay_hours"]
            severity = result["max_severity"]
        else:
            weather_data = fetch_marine_weather(target_lat, target_lon, timeout)
            if weather_data:
                max_wave, max_wind, _, _ = extract_weather_conditions(weather_data, eta)
                result = predictor.predict_delay(
                    wave_height_m=max_wave,
                    wind_speed_kt=max_wind,
                    vessel_size_teu=vessel_size,
                )
                delay_hours = result["delay_hours"]
                severity = result["severity"]
            else:
                delay_hours = 0.0
                severity = "none"

        summary_item = None
        if delay_hours > 0:
            adjusted_eta = eta + timedelta(hours=delay_hours)
            vessel["eta"] = adjusted_eta.strftime(ETA_FORMAT)
            summary_item = {
                "vessel_id": str(vessel.get("vessel_id", "?")),
                "vessel_name": str(vessel.get("name", "Unknown")),
                "origin_lat": vessel.get("origin_lat"),
                "origin_lon": vessel.get("origin_lon"),
                "origin_port": vessel.get("origin_port"),
                "dest_lat": vessel.get("dest_lat"),
                "dest_lon": vessel.get("dest_lon"),
                "dest_port": vessel.get("dest_port"),
                "delay_hours": round(delay_hours, 2),
                "severity": severity,
            }

        vessel["weather_delay_hours"] = delay_hours
        vessel["weather_severity"] = severity
        return vessel, summary_item

    enriched_vessels: list[Row] = []
    weather_summary: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_vessel, v) for v in vessels_to_process]
        for future in futures:
            try:
                v_res, summary_res = future.result()
                enriched_vessels.append(v_res)
                if summary_res:
                    weather_summary.append(summary_res)
            except Exception as err:
                logger.warning("Error evaluating weather delay for vessel: %s", err)

    for v in capped_vessels:
        v_copy = dict(v)
        v_copy["weather_delay_hours"] = 0.0
        v_copy["weather_severity"] = "none"
        enriched_vessels.append(v_copy)

    return enriched_vessels, weather_summary


# Global predictor instance for reuse
_predictor: WeatherPredictor | None = None


def get_weather_predictor() -> WeatherPredictor:
    """Get or create the global weather predictor instance."""
    global _predictor
    if _predictor is None:
        _predictor = WeatherPredictor()
    return _predictor
