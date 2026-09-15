"""IBM watsonx.ai text-generation client.

Design notes:

* State (IAM token cache, auth circuit breaker) lives on the instance rather than
  in module globals, so tests get isolation and the object can be swapped out.
* Transient failures (429/5xx, network errors) are retried with jittered
  exponential backoff. Client errors (400/401/403) are never retried.
* After an authentication failure the client short-circuits token requests for a
  cooldown period instead of hammering IAM once per vessel.
* Upstream response bodies are logged at DEBUG but never embedded verbatim in
  exception messages, which can end up in user-facing error surfaces.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from functools import lru_cache
from typing import Any

import requests

from portpulse.config import WatsonxSettings, get_settings

logger = logging.getLogger(__name__)

#: Status codes worth retrying. Everything else (notably 400/401/403) is returned
#: immediately, because retrying a rejected credential only wastes time.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_LOGGED_BODY = 500


class WatsonxError(RuntimeError):
    """Base class for watsonx.ai client failures."""


class WatsonxNotConfiguredError(WatsonxError):
    """Raised when credentials are absent, so no call was attempted."""


class WatsonxAuthError(WatsonxError):
    """Raised when an IAM access token could not be obtained."""


class WatsonxGenerationError(WatsonxError):
    """Raised when the text-generation endpoint failed or returned an odd payload."""


def _safe_reason(response: requests.Response) -> str:
    """Extract a short, non-sensitive reason from an error response."""
    try:
        payload = response.json()
    except ValueError:
        return response.reason or "unknown error"

    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            message = errors[0].get("message")
            if message:
                return str(message)[:200]
        for key in ("errorMessage", "message", "error_description", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value[:200]
    return response.reason or "unknown error"


class WatsonxClient:
    """Thin REST client for the watsonx.ai text-generation API."""

    def __init__(
        self,
        settings: WatsonxSettings | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._settings = settings or get_settings().watsonx
        self._session = session or requests.Session()
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expiry = 0.0
        self._last_auth_failure = 0.0

    @property
    def settings(self) -> WatsonxSettings:
        return self._settings

    @property
    def enabled(self) -> bool:
        """True when credentials are configured and calls are worth attempting."""
        return self._settings.enabled

    def reset_cache(self) -> None:
        """Clear the cached token and the auth circuit breaker."""
        with self._lock:
            self._token = None
            self._token_expiry = 0.0
            self._last_auth_failure = 0.0

    # ── HTTP plumbing ────────────────────────────────────────────────────────

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
                delay = self._backoff_delay(backoff, attempt)
                logger.warning(
                    "Network error calling watsonx.ai (attempt %d/%d): %s. Retrying in %.2fs.",
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
            delay = self._backoff_delay(backoff, attempt)
            logger.warning(
                "watsonx.ai returned HTTP %d (attempt %d/%d). Retrying in %.2fs.",
                response.status_code,
                attempt,
                retries,
                delay,
            )
            time.sleep(delay)

        if last_response is not None:
            return last_response
        raise WatsonxGenerationError(f"Request to {url} failed after {retries} attempts.")

    @staticmethod
    def _backoff_delay(backoff_factor: float, attempt: int) -> float:
        """Exponential backoff with jitter to avoid synchronised retry storms."""
        base = backoff_factor * (2 ** (attempt - 1))
        return base * (1.0 + random.random() * 0.25)

    # ── IAM ──────────────────────────────────────────────────────────────────

    def _iam_token(self) -> str:
        """Return a cached or freshly fetched IAM access token.

        Fast path is an unlocked read of the cached token. The slow path holds the
        lock across the circuit-breaker check, the cache re-check, the network
        fetch and the cache write so they behave as one critical section.
        """
        api_key = self._settings.api_key
        if not api_key:
            raise WatsonxNotConfiguredError("WATSONX_API_KEY is not configured.")

        if api_key.startswith(("bob_", "bearer_", "ey")):
            return api_key

        now = time.monotonic()
        token = self._token
        if token and now < self._token_expiry:
            return token

        with self._lock:
            now = time.monotonic()
            cooldown = self._settings.auth_cooldown_seconds
            if self._last_auth_failure and now - self._last_auth_failure < cooldown:
                raise WatsonxAuthError(
                    "Skipping IAM request: a recent authentication failure is still in cooldown."
                )
            if self._token and now < self._token_expiry:
                return self._token

            fetch_start = time.monotonic()
            try:
                response = self._request_with_retry(
                    "POST",
                    self._settings.iam_url,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                    },
                    data={
                        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                        "apikey": api_key,
                    },
                    timeout=self._settings.iam_timeout_seconds,
                )
            except requests.RequestException as err:
                self._last_auth_failure = time.monotonic()
                raise WatsonxAuthError(f"Could not reach IBM IAM: {err}") from err

            if response.status_code != 200:
                self._last_auth_failure = time.monotonic()
                logger.debug("IAM error body: %s", response.text[:_MAX_LOGGED_BODY])
                raise WatsonxAuthError(
                    f"IAM token request failed (HTTP {response.status_code}): "
                    f"{_safe_reason(response)}"
                )

            try:
                payload = response.json()
            except ValueError as err:
                self._last_auth_failure = time.monotonic()
                raise WatsonxAuthError("IAM returned a non-JSON response.") from err

            token = payload.get("access_token")
            if not token:
                self._last_auth_failure = time.monotonic()
                raise WatsonxAuthError("IAM response did not contain an access_token.")

            expires_in = int(payload.get("expires_in", 3600))
            buffer = self._settings.token_expiry_buffer_seconds
            self._token = str(token)
            self._token_expiry = fetch_start + max(0, expires_in - buffer)
            self._last_auth_failure = 0.0
            logger.debug("Obtained IAM token, valid for ~%ds.", max(0, expires_in - buffer))
            return self._token

    # ── Generation ───────────────────────────────────────────────────────────

    def generate_text(self, prompt: str) -> str:
        """Generate text for ``prompt``.

        Raises:
            WatsonxNotConfiguredError: if credentials are missing.
            WatsonxAuthError: if IAM authentication fails.
            WatsonxGenerationError: if the generation call fails or returns
                an unexpected payload.
        """
        if not self._settings.enabled:
            raise WatsonxNotConfiguredError(
                "watsonx.ai is not configured: set WATSONX_API_KEY and WATSONX_PROJECT_ID."
            )

        token = self._iam_token()
        try:
            response = self._request_with_retry(
                "POST",
                self._settings.generation_endpoint,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "input": prompt,
                    "parameters": {
                        "decoding_method": "greedy",
                        "max_new_tokens": self._settings.max_new_tokens,
                        "min_new_tokens": 1,
                    },
                    "model_id": self._settings.model_id,
                    "project_id": self._settings.project_id,
                },
                timeout=self._settings.request_timeout_seconds,
            )
        except requests.RequestException as err:
            raise WatsonxGenerationError(f"Could not reach watsonx.ai: {err}") from err

        if response.status_code not in (200, 201):
            logger.debug("Generation error body: %s", response.text[:_MAX_LOGGED_BODY])
            raise WatsonxGenerationError(
                f"Text generation failed (HTTP {response.status_code}): {_safe_reason(response)}"
            )

        try:
            payload = response.json()
            generated = None
            results = payload.get("results")
            choices = payload.get("choices")
            if isinstance(results, list) and results:
                first_res = results[0]
                if isinstance(first_res, dict) and "generated_text" in first_res:
                    generated = first_res["generated_text"]
            elif isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    msg = choice.get("message")
                    if isinstance(msg, dict) and "content" in msg:
                        generated = msg["content"]
                    elif "text" in choice:
                        generated = choice["text"]
                elif "reply" in payload:
                    generated = payload["reply"]
                elif "response" in payload:
                    generated = payload["response"]
                elif "content" in payload:
                    generated = payload["content"]

            if generated is None:
                raise WatsonxGenerationError("Unexpected response payload from watsonx.ai.")
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise WatsonxGenerationError("Unexpected response payload from watsonx.ai.") from err

        return str(generated).strip()


@lru_cache(maxsize=1)
def get_client() -> WatsonxClient:
    """Return the process-wide watsonx client."""
    return WatsonxClient()


def reset_client_cache() -> None:
    """Drop the cached client (used by tests and after a settings change)."""
    get_client.cache_clear()
