"""Google Gemini text-generation client.

Design notes:
* Uses Google Generative Language REST API (`/v1beta/models/{model}:generateContent`).
* Retries transient network/server errors with exponential backoff.
* Parses candidate output parts cleanly and raises explicit GeminiError types on failure.
"""

from __future__ import annotations

import logging
import random
import time
from functools import lru_cache
from typing import Any

import requests

from portpulse.config import GeminiSettings, get_settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_LOGGED_BODY = 500


class GeminiError(RuntimeError):
    """Base exception for Google Gemini client failures."""


class GeminiNotConfiguredError(GeminiError):
    """Raised when GEMINI_API_KEY is not configured."""


class GeminiGenerationError(GeminiError):
    """Raised when text generation API call fails or returns invalid response."""


def _safe_reason(response: requests.Response) -> str:
    """Extract a short, safe error message from response body."""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                msg = err.get("message")
                if msg:
                    return str(msg)[:200]
    except Exception:
        pass
    return response.reason or "unknown error"


class GeminiClient:
    """Thin REST client for Google Gemini text-generation API."""

    def __init__(
        self,
        settings: GeminiSettings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._settings = settings or get_settings().gemini
        self._session = session or requests.Session()

    @property
    def settings(self) -> GeminiSettings:
        return self._settings

    @property
    def enabled(self) -> bool:
        """True when a valid Gemini API key is configured."""
        return self._settings.enabled

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        retries = self._settings.max_retries
        backoff = self._settings.backoff_factor
        last_response: requests.Response | None = None

        for attempt in range(1, retries + 1):
            try:
                response = self._session.request(method, url, **kwargs)
            except requests.RequestException as err:
                if attempt == retries:
                    raise
                delay = backoff * (2 ** (attempt - 1)) * (1.0 + random.random() * 0.25)
                logger.warning(
                    "Network error calling Gemini API (attempt %d/%d): %s. Retrying in %.2fs.",
                    attempt,
                    retries,
                    err,
                    delay,
                )
                time.sleep(delay)
                continue

            if response.status_code not in _RETRYABLE_STATUS:
                return response

            last_response = response
            if attempt == retries:
                break
            delay = backoff * (2 ** (attempt - 1)) * (1.0 + random.random() * 0.25)
            logger.warning(
                "Gemini API returned HTTP %d (attempt %d/%d). Retrying in %.2fs.",
                response.status_code,
                attempt,
                retries,
                delay,
            )
            time.sleep(delay)

        if last_response is not None:
            return last_response
        raise GeminiGenerationError(f"Request to Gemini API failed after {retries} attempts.")

    def generate_text(self, prompt: str) -> str:
        """Generate text using Google Gemini API.

        Raises:
            GeminiNotConfiguredError: if API key is not configured.
            GeminiGenerationError: if HTTP request fails or payload is malformed.
        """
        if not self._settings.enabled:
            raise GeminiNotConfiguredError(
                "Gemini API key is not configured: set GEMINI_API_KEY environment variable."
            )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        }

        try:
            response = self._request_with_retry(
                "POST",
                self._settings.generation_endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=self._settings.request_timeout_seconds,
            )
        except requests.RequestException as err:
            raise GeminiGenerationError(f"Could not reach Gemini API: {err}") from err

        if response.status_code not in (200, 201):
            logger.debug("Gemini error body: %s", response.text[:_MAX_LOGGED_BODY])
            raise GeminiGenerationError(
                f"Gemini generation failed (HTTP {response.status_code}): {_safe_reason(response)}"
            )

        try:
            res_data = response.json()
            candidates = res_data.get("candidates")
            if isinstance(candidates, list) and candidates:
                first_cand = candidates[0]
                if isinstance(first_cand, dict):
                    content = first_cand.get("content")
                    if isinstance(content, dict):
                        parts = content.get("parts")
                        if isinstance(parts, list) and parts:
                            text = parts[0].get("text")
                            if text:
                                return str(text).strip()

            raise GeminiGenerationError("Unexpected response structure from Gemini API.")
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise GeminiGenerationError("Unexpected response payload from Gemini API.") from err


@lru_cache(maxsize=1)
def get_gemini_client() -> GeminiClient:
    """Return the process-wide Gemini client."""
    return GeminiClient()


def reset_gemini_client_cache() -> None:
    """Drop the cached Gemini client (used by tests and after settings change)."""
    get_gemini_client.cache_clear()
