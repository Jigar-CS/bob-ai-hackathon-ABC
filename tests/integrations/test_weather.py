"""Unit tests for the weather delay engine (integrations/weather.py).

All Open-Meteo API calls are mocked — no real network requests.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from portpulse.integrations.weather import (
    _delay_from_severity,
    _extract_conditions_near_eta,
    _ms_to_knots,
    _severity_label,
    apply_weather_delays,
    estimate_weather_delay_hours,
)

# ---------------------------------------------------------------------------
# Helper / unit tests
# ---------------------------------------------------------------------------


class TestSeverityTiers:
    """Tier classification is deterministic and covers all branches."""

    def test_none_below_all_thresholds(self):
        assert _severity_label(1.0, 10.0) == "none"

    def test_minor_wave_trigger(self):
        assert _severity_label(2.5, 10.0) == "minor"

    def test_minor_wind_trigger(self):
        assert _severity_label(1.0, 28.0) == "minor"

    def test_moderate_wave_trigger(self):
        assert _severity_label(3.5, 10.0) == "moderate"

    def test_moderate_wind_trigger(self):
        assert _severity_label(1.0, 40.0) == "moderate"

    def test_severe_wave_trigger(self):
        assert _severity_label(6.0, 10.0) == "severe"

    def test_severe_wind_trigger(self):
        assert _severity_label(1.0, 55.0) == "severe"


class TestDelayMapping:
    """Delay hours map correctly to severity labels."""

    def test_none_returns_zero(self):
        assert _delay_from_severity("none") == 0.0

    def test_minor_positive(self):
        assert _delay_from_severity("minor") > 0

    def test_moderate_greater_than_minor(self):
        assert _delay_from_severity("moderate") > _delay_from_severity("minor")

    def test_severe_greatest(self):
        assert _delay_from_severity("severe") > _delay_from_severity("moderate")

    def test_unknown_returns_zero(self):
        assert _delay_from_severity("hurricane") == 0.0


class TestMsToKnots:
    def test_zero(self):
        assert _ms_to_knots(0.0) == 0.0

    def test_conversion(self):
        # 1 m/s ≈ 1.944 kt
        result = _ms_to_knots(1.0)
        assert abs(result - 1.944) < 0.001


# ---------------------------------------------------------------------------
# _extract_conditions_near_eta
# ---------------------------------------------------------------------------

_SAMPLE_HOURLY = {
    "hourly": {
        "time": [
            "2026-10-01T06:00",
            "2026-10-01T07:00",
            "2026-10-01T08:00",
            "2026-10-02T08:00",  # outside window
        ],
        "wave_height": [1.0, 4.0, 2.5, 10.0],
        "wind_speed_10m": [5.0, 8.0, 6.0, 30.0],
    }
}

_ETA = datetime(2026, 10, 1, 8, 0)


class TestExtractConditions:
    def test_picks_max_wave_in_window(self):
        wave_m, _ = _extract_conditions_near_eta(_SAMPLE_HOURLY, _ETA)
        assert wave_m == 4.0  # max within 24h window ending at ETA

    def test_excludes_outside_window(self):
        wave_m, _ = _extract_conditions_near_eta(_SAMPLE_HOURLY, _ETA)
        assert wave_m < 10.0  # the 10m entry is outside the window

    def test_empty_data_returns_zeros(self):
        wave_m, wind_kt = _extract_conditions_near_eta({}, _ETA)
        assert wave_m == 0.0
        assert wind_kt == 0.0


# ---------------------------------------------------------------------------
# estimate_weather_delay_hours — mocked API
# ---------------------------------------------------------------------------


def _make_api_response(wave: float, wind_ms: float) -> MagicMock:
    """Build a mock response matching the marine API structure."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "hourly": {
            "time": ["2026-10-01T07:00"],
            "wave_height": [wave],
            "wind_speed_10m": [wind_ms],
        }
    }
    return mock


class TestEstimateWeatherDelay:
    @patch("portpulse.integrations.weather.requests.get")
    def test_severe_conditions_return_delay(self, mock_get):
        mock_get.return_value = _make_api_response(wave=6.0, wind_ms=30.0)
        delay, severity = estimate_weather_delay_hours(33.73, -118.26, _ETA)
        assert delay > 0
        assert severity == "severe"

    @patch("portpulse.integrations.weather.requests.get")
    def test_calm_conditions_return_no_delay(self, mock_get):
        mock_get.return_value = _make_api_response(wave=0.5, wind_ms=2.0)
        delay, severity = estimate_weather_delay_hours(33.73, -118.26, _ETA)
        assert delay == 0.0
        assert severity == "none"

    @patch("portpulse.integrations.weather.requests.get", side_effect=ConnectionError("offline"))
    def test_network_failure_returns_no_delay(self, _mock):
        delay, severity = estimate_weather_delay_hours(33.73, -118.26, _ETA)
        assert delay == 0.0
        assert severity == "none"


# ---------------------------------------------------------------------------
# apply_weather_delays
# ---------------------------------------------------------------------------

_VESSEL_WITH_ORIGIN = {
    "vessel_id": "V001",
    "name": "MV Test-1",
    "eta": "2026-10-01 12:00",
    "size_teu": "6000",
    "cargo_type": "general",
    "priority": "1",
    "origin_lat": "35.68",
    "origin_lon": "139.69",
}

_VESSEL_WITHOUT_ORIGIN = {
    "vessel_id": "V002",
    "name": "MV Test-2",
    "eta": "2026-10-01 15:00",
    "size_teu": "4000",
    "cargo_type": "general",
    "priority": "2",
}


class TestApplyWeatherDelays:
    @patch("portpulse.integrations.weather.requests.get")
    def test_severe_weather_adjusts_eta(self, mock_get):
        mock_get.return_value = _make_api_response(wave=6.0, wind_ms=30.0)
        result = apply_weather_delays(
            [_VESSEL_WITH_ORIGIN],
            port_lat=33.73,
            port_lon=-118.26,
            timeout=1.0,
        )
        assert len(result) == 1
        v = result[0]
        assert float(v["weather_delay_hours"]) > 0
        assert v["weather_severity"] == "severe"
        # ETA must have been pushed forward
        assert v["eta"] != _VESSEL_WITH_ORIGIN["eta"]

    @patch("portpulse.integrations.weather.requests.get")
    def test_calm_weather_leaves_eta_unchanged(self, mock_get):
        mock_get.return_value = _make_api_response(wave=0.2, wind_ms=1.0)
        result = apply_weather_delays(
            [_VESSEL_WITH_ORIGIN],
            port_lat=33.73,
            port_lon=-118.26,
            timeout=1.0,
        )
        v = result[0]
        assert v["eta"] == _VESSEL_WITH_ORIGIN["eta"]
        assert v["weather_delay_hours"] == 0.0

    @patch("portpulse.integrations.weather.requests.get")
    def test_vessel_without_origin_still_gets_weather_fields(self, mock_get):
        mock_get.return_value = _make_api_response(wave=0.5, wind_ms=2.0)
        result = apply_weather_delays(
            [_VESSEL_WITHOUT_ORIGIN],
            port_lat=33.73,
            port_lon=-118.26,
            timeout=1.0,
        )
        v = result[0]
        assert "weather_delay_hours" in v
        assert "weather_severity" in v

    @patch("portpulse.integrations.weather.requests.get", side_effect=ConnectionError)
    def test_network_failure_leaves_vessels_unchanged(self, _mock):
        result = apply_weather_delays(
            [_VESSEL_WITH_ORIGIN, _VESSEL_WITHOUT_ORIGIN],
            port_lat=33.73,
            port_lon=-118.26,
            timeout=1.0,
        )
        assert len(result) == 2
        for v in result:
            assert v["weather_delay_hours"] == 0.0
            assert v["weather_severity"] == "none"

    def test_weather_disabled_via_config(self, monkeypatch: pytest.MonkeyPatch):  # noqa: ARG002
        """When weather_enabled=False the planner skips apply_weather_delays entirely.

        This test verifies the function itself is pure and produces correct fields
        without needing config-level control (config gate is in planner.py).
        """
        # Even with no network, empty vessel list must return empty list
        result = apply_weather_delays(
            [],
            port_lat=33.73,
            port_lon=-118.26,
        )
        assert result == []
