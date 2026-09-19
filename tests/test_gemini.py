"""Unit tests for Google Gemini integration and settings."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from portpulse.config import GeminiSettings
from portpulse.integrations.gemini import (
    GeminiClient,
    GeminiGenerationError,
    GeminiNotConfiguredError,
    get_gemini_client,
    reset_gemini_client_cache,
)


@pytest.fixture
def gemini_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key_123")


def test_gemini_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("PORTPULSE_GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-flash-latest")

    settings = GeminiSettings()
    assert settings.api_key is None
    assert settings.enabled is False
    assert settings.model_id == "gemini-flash-latest"


def test_gemini_settings_with_key(gemini_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-flash-latest")
    settings = GeminiSettings()
    assert settings.api_key == "test_gemini_key_123"
    assert settings.enabled is True
    endpoint = settings.generation_endpoint
    assert "models/gemini-flash-latest:generateContent?key=test_gemini_key_123" in endpoint


def test_gemini_client_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("PORTPULSE_GEMINI_API_KEY", "")

    settings = GeminiSettings()

    client = GeminiClient(settings=settings)
    assert client.enabled is False
    with pytest.raises(GeminiNotConfiguredError):
        client.generate_text("Hello")


def test_gemini_client_generate_text_success(gemini_env: None) -> None:
    settings = GeminiSettings()
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "  Vessel V101 is scheduled at Berth B1.  "}]}}
        ]
    }
    mock_session.request.return_value = mock_resp

    client = GeminiClient(settings=settings, session=mock_session)
    result = client.generate_text("What is V101 status?")

    assert result == "Vessel V101 is scheduled at Berth B1."
    mock_session.request.assert_called_once()


def test_gemini_client_http_error(gemini_env: None) -> None:
    settings = GeminiSettings(max_retries=1)
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.reason = "Bad Request"
    mock_resp.json.return_value = {"error": {"message": "Invalid API Key"}}
    mock_session.request.return_value = mock_resp

    client = GeminiClient(settings=settings, session=mock_session)
    with pytest.raises(GeminiGenerationError) as exc_info:
        client.generate_text("Test question")

    assert "Invalid API Key" in str(exc_info.value)


def test_gemini_client_retry_and_success(gemini_env: None) -> None:
    settings = GeminiSettings(max_retries=2, backoff_factor=0.01)
    mock_session = MagicMock()

    resp_fail = MagicMock()
    resp_fail.status_code = 503

    resp_ok = MagicMock()
    resp_ok.status_code = 200
    resp_ok.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Berth B2 is operational."}]}}]
    }

    mock_session.request.side_effect = [resp_fail, resp_ok]

    client = GeminiClient(settings=settings, session=mock_session)
    result = client.generate_text("Status of Berth B2?")
    assert result == "Berth B2 is operational."
    assert mock_session.request.call_count == 2


def test_gemini_singleton_cache() -> None:
    reset_gemini_client_cache()
    c1 = get_gemini_client()
    c2 = get_gemini_client()
    assert c1 is c2
    reset_gemini_client_cache()
