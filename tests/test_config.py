"""Configuration behaviour: placeholder handling, parsing and defaults."""

from __future__ import annotations

import pytest

from portpulse.config import AppSettings, WatsonxSettings, get_settings, reset_settings_cache


@pytest.mark.parametrize(
    "placeholder",
    ["your_api_key_here", "  your_project_id_here ", "", "   ", "changeme", "<api-key>"],
)
def test_placeholder_credentials_are_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch, placeholder: str
) -> None:
    """An untouched .env.example must not look like working credentials.

    Otherwise the client burns retries against IAM once per vessel before falling back.
    """
    monkeypatch.setenv("WATSONX_API_KEY", placeholder)
    monkeypatch.setenv("WATSONX_PROJECT_ID", placeholder)
    settings = WatsonxSettings()
    assert settings.api_key is None
    assert settings.project_id is None
    assert settings.enabled is False


def test_real_credentials_enable_watsonx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATSONX_API_KEY", "abc123realkey")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "8f2c-project")
    settings = WatsonxSettings()
    assert settings.enabled is True


def test_bob_agent_api_key_enables_watsonx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATSONX_API_KEY", raising=False)
    monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
    monkeypatch.setenv("BOB_AGENT_API_KEY", "bob_secret_key_12345")
    settings = WatsonxSettings()
    assert settings.api_key == "bob_secret_key_12345"
    assert settings.project_id == "bob-agent-project"
    assert settings.enabled is True


def test_generation_endpoint_has_no_double_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATSONX_URL", "https://eu-de.ml.cloud.ibm.com/")
    settings = WatsonxSettings()
    assert settings.generation_endpoint.startswith("https://eu-de.ml.cloud.ibm.com/ml/v1/")
    assert "//ml" not in settings.generation_endpoint


def test_cors_origins_parsed_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PORTPULSE_CORS_ALLOW_ORIGINS", "https://ops.example.com, https://admin.example.com ,"
    )
    assert AppSettings().cors_origins == [
        "https://ops.example.com",
        "https://admin.example.com",
    ]


def test_dataset_paths_derive_from_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTPULSE_DATA_DIR", "/srv/portpulse/data")
    settings = AppSettings()
    assert settings.vessels_path.name == "vessels.csv"
    assert settings.berths_path.parent == settings.data_dir
    assert settings.alternate_ports_path.name == "alternate_ports.json"


def test_invalid_setting_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORTPULSE_MAX_BERTH_WAIT_HOURS", "-4")
    with pytest.raises(ValueError, match="max_berth_wait_hours"):
        AppSettings()


def test_settings_are_cached_until_reset() -> None:
    first = get_settings()
    assert get_settings() is first
    reset_settings_cache()
    assert get_settings() is not first


def test_crane_settings_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = AppSettings()
    assert defaults.baseline_crane_count == 4
    assert defaults.crane_dwell_min_multiplier == 0.5
    assert defaults.crane_dwell_max_multiplier == 2.0

    monkeypatch.setenv("PORTPULSE_BASELINE_CRANE_COUNT", "6")
    monkeypatch.setenv("PORTPULSE_CRANE_DWELL_MIN_MULTIPLIER", "0.3")
    monkeypatch.setenv("PORTPULSE_CRANE_DWELL_MAX_MULTIPLIER", "3.0")
    custom = AppSettings()
    assert custom.baseline_crane_count == 6
    assert custom.crane_dwell_min_multiplier == 0.3
    assert custom.crane_dwell_max_multiplier == 3.0
