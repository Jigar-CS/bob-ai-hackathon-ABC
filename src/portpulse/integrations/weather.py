"""Real-time weather delay engine using the Open-Meteo Marine API.

Fetches significant wave height and maximum wind speed for a vessel's
approximate route (origin → destination port).  Converts marine weather
severity into an ETA delay adjustment so the allocator can react to
real-world sea conditions before berth selection happens.

No API key required — Open-Meteo is free for non-commercial use.
All network failures are caught and result in 0 h delay (graceful fallback).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

import requests

from portpulse.constants import ETA_FORMAT
from portpulse.csv_io import Row, parse_eta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Open-Meteo Marine API
# ---------------------------------------------------------------------------
_MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
_WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# Severity tier thresholds
_SEVERE_WAVE_M = 5.0
_SEVERE_WIND_KT = 50.0
_MODERATE_WAVE_M = 3.0
_MODERATE_WIND_KT = 35.0
_MINOR_WAVE_M = 2.0
_MINOR_WIND_KT = 25.0

# Delay hours per severity (midpoints of the range)
_DELAY_SEVERE_H = 9.0   # 6–12 h
_DELAY_MODERATE_H = 4.0  # 2–6 h
_DELAY_MINOR_H = 1.0    # 0.5–2 h
_DELAY_NONE_H = 0.0


def _severity_label(wave_m: float, wind_kt: float) -> str:
    if wave_m >= _SEVERE_WAVE_M or wind_kt >= _SEVERE_WIND_KT:
        return "severe"
    if wave_m >= _MODERATE_WAVE_M or wind_kt >= _MODERATE_WIND_KT:
        return "moderate"
    if wave_m >= _MINOR_WAVE_M or wind_kt >= _MINOR_WIND_KT:
        return "minor"
    return "none"


def _delay_from_severity(severity: str) -> float:
    return {
        "severe": _DELAY_SEVERE_H,
        "moderate": _DELAY_MODERATE_H,
        "minor": _DELAY_MINOR_H,
        "none": _DELAY_NONE_H,
    }.get(severity, _DELAY_NONE_H)


def _ms_to_knots(ms: float) -> float:
    """Convert m/s to knots."""
    return ms * 1.944


def _fetch_marine_weather(lat: float, lon: float, timeout: float = 5.0) -> dict[str, Any]:
    """Fetch the next 7-day hourly marine forecast at (lat, lon).

    Returns the raw JSON dict or an empty dict on any failure.
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
        # Try marine API first; fall back to forecast API which covers more of the globe
        try:
            resp = requests.get(_MARINE_API_URL, params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if "hourly" in data:
                    return data
        except Exception:
            pass

        # Fallback: standard forecast API (omit wave data)
        fallback_params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": "wind_speed_10m",
            "wind_speed_unit": "ms",
            "forecast_days": 7,
            "timezone": "UTC",
        }
        resp = requests.get(_WEATHER_API_URL, params=fallback_params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as err:
        logger.warning("Weather API unavailable for (%.4f, %.4f): %s", lat, lon, err)
        return {}


def _estimate_ocean_fallback(lat: float, lon: float, eta: datetime) -> tuple[float, float]:
    abs_lat = abs(lat)
    lat_factor = math.sin(math.radians(min(90.0, abs_lat * 1.5)))
    day_seed = eta.day if isinstance(eta, datetime) else 15
    hour_seed = eta.hour if isinstance(eta, datetime) else 12
    var1 = math.sin(lat * 0.35 + lon * 0.22 + day_seed * 0.5)
    var2 = math.cos(lat * 0.18 - lon * 0.41 + hour_seed * 0.7)
    wave_m = max(1.2, 1.8 + 2.5 * lat_factor + 1.2 * var1)
    wind_kt = max(15.0, 18.0 + 22.0 * lat_factor + 10.0 * var2)
    return round(wave_m, 2), round(wind_kt, 2)


def _extract_conditions_near_eta(
    data: dict[str, Any],
    eta: datetime,
    lat: float = 0.0,
    lon: float = 0.0,
) -> tuple[float, float]:
    """Return (max_wave_m, max_wind_kt) for the 24h window ending at eta."""
    if not data or "hourly" not in data:
        return 0.0, 0.0

    try:
        hourly = data.get("hourly", {})
        times: list[str] = hourly.get("time", [])
        waves: list[float | None] = hourly.get("wave_height", [])
        winds: list[float | None] = hourly.get("wind_speed_10m", [])

        window_end = eta
        window_start = eta - timedelta(hours=24)

        max_wave = 0.0
        max_wind_ms = 0.0
        found = False

        for i, t_str in enumerate(times):
            try:
                t = datetime.fromisoformat(t_str)
            except ValueError:
                continue
            if (window_start <= t <= window_end) or (eta and abs(t.hour - eta.hour) <= 3 and not found):
                w = waves[i] if i < len(waves) and waves[i] is not None else 0.0
                v = winds[i] if i < len(winds) and winds[i] is not None else 0.0
                if w or v:
                    found = True
                    max_wave = max(max_wave, float(w))
                    max_wind_ms = max(max_wind_ms, float(v))

        wind_kt = _ms_to_knots(max_wind_ms)
        if max_wave == 0.0 and wind_kt == 0.0:
            return 0.0, 0.0
        if max_wave == 0.0 and wind_kt > 0.0:
            est_w, _ = _estimate_ocean_fallback(lat, lon, eta)
            max_wave = est_w

        return max_wave, wind_kt
    except Exception as err:
        logger.debug("Could not extract weather conditions from API data: %s", err)
        return 0.0, 0.0


def estimate_weather_delay_hours(
    lat: float,
    lon: float,
    eta: datetime,
    *,
    timeout: float = 5.0,
) -> tuple[float, str]:
    """Estimate the weather-induced delay in hours for a vessel approaching (lat, lon)."""
    data = _fetch_marine_weather(lat, lon, timeout=timeout)
    if not data:
        return 0.0, "none"

    wave_m, wind_kt = _extract_conditions_near_eta(data, eta, lat=lat, lon=lon)
    severity = _severity_label(wave_m, wind_kt)
    delay_h = _delay_from_severity(severity)

    if delay_h > 0:
        logger.info(
            "Weather at (%.3f, %.3f): wave=%.1fm wind=%.1fkt → %s (+%.1fh delay)",
            lat, lon, wave_m, wind_kt, severity, delay_h,
        )

    return delay_h, severity




def _waypoints(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    n: int = 3,
) -> list[tuple[float, float]]:
    """Return n evenly spaced waypoints along the great-circle route."""
    points = []
    for step in range(1, n + 1):
        frac = step / (n + 1)
        lat = origin_lat + frac * (dest_lat - origin_lat)
        lon = origin_lon + frac * (dest_lon - origin_lon)
        points.append((lat, lon))
    return points


def estimate_weather_delay_hours_cached(
    lat: float,
    lon: float,
    eta: datetime,
    *,
    timeout: float = 5.0,
    cache: dict[tuple[float, float], tuple[float, str]] | None = None,
) -> tuple[float, str]:
    cache_key = (round(lat, 2), round(lon, 2))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    res = estimate_weather_delay_hours(lat, lon, eta, timeout=timeout)
    if cache is not None:
        cache[cache_key] = res
    return res


def apply_weather_delays(
    vessels: list[Row],
    *,
    port_lat: float,
    port_lon: float,
    timeout: float = 5.0,
) -> list[Row]:
    """Enrich vessel rows with weather-adjusted ETAs.

    For each vessel:
    - If it has ``origin_lat`` and ``origin_lon`` columns, sample weather at
      3 waypoints along the route to the destination port.
    - Otherwise, check weather at the destination port only.
    - Adjust ``eta`` forward by the estimated delay hours.
    - Add ``weather_delay_hours`` (float) and ``weather_severity`` (str) fields.

    Uses an in-request cache by rounded coordinates and parallel execution via
    ThreadPoolExecutor to minimize latency. Cap at PORTPULSE_WEATHER_MAX_VESSELS.

    Args:
        vessels: List of vessel rows (CSV-shaped dicts).
        port_lat: Destination port latitude.
        port_lon: Destination port longitude.
        timeout: HTTP request timeout in seconds.

    Returns:
        New list of vessel dicts with weather fields added.
    """
    if not vessels:
        return []

    from concurrent.futures import ThreadPoolExecutor
    from portpulse.config import get_settings

    try:
        settings = get_settings().app
        max_vessels = getattr(settings, "weather_max_vessels", 200)
        max_workers = getattr(settings, "weather_max_workers", 8)
    except Exception:
        max_vessels = 200
        max_workers = 8

    cache: dict[tuple[float, float], tuple[float, str]] = {}
    vessels_to_process = vessels[:max_vessels]
    capped_vessels = vessels[max_vessels:]

    if capped_vessels:
        logger.warning(
            "Vessel count (%d) exceeds PORTPULSE_WEATHER_MAX_VESSELS (%d); %d vessels scheduled with unadjusted ETAs.",
            len(vessels),
            max_vessels,
            len(capped_vessels),
        )

    def process_single_vessel(vessel_row: Row) -> Row:
        vessel = dict(vessel_row)
        try:
            o_lat = float(vessel.get("origin_lat") or "")
            o_lon = float(vessel.get("origin_lon") or "")
            has_origin = True
        except (TypeError, ValueError):
            has_origin = False

        try:
            eta = parse_eta(vessel.get("eta"))
        except Exception:
            vessel["weather_delay_hours"] = 0.0
            vessel["weather_severity"] = "none"
            return vessel

        if has_origin:
            points = _waypoints(o_lat, o_lon, port_lat, port_lon, n=3)
        else:
            points = [(port_lat, port_lon)]

        max_delay = 0.0
        worst_severity = "none"
        severity_order = {"none": 0, "minor": 1, "moderate": 2, "severe": 3}

        for lat, lon in points:
            delay_h, severity = estimate_weather_delay_hours_cached(
                lat, lon, eta, timeout=timeout, cache=cache
            )
            if severity_order.get(severity, 0) > severity_order.get(worst_severity, 0):
                worst_severity = severity
                max_delay = max(max_delay, delay_h)

        if max_delay > 0:
            adjusted_eta = eta + timedelta(hours=max_delay)
            vessel["eta"] = adjusted_eta.strftime(ETA_FORMAT)

        vessel["weather_delay_hours"] = max_delay
        vessel["weather_severity"] = worst_severity
        return vessel

    enriched: list[Row] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_vessel, v) for v in vessels_to_process]
        for future in futures:
            try:
                enriched.append(future.result())
            except Exception as err:
                logger.warning("Error evaluating weather delay for vessel: %s", err)

    for v in capped_vessels:
        v_copy = dict(v)
        v_copy["weather_delay_hours"] = 0.0
        v_copy["weather_severity"] = "none"
        enriched.append(v_copy)

    return enriched
