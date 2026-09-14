"""watsonx.ai client: auth caching, retries, circuit breaker and error hygiene."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from portpulse.config import WatsonxSettings
from portpulse.integrations.watsonx import (
    WatsonxAuthError,
    WatsonxClient,
    WatsonxGenerationError,
    WatsonxNotConfiguredError,
    get_client,
    reset_client_cache,
)

SECRET_BODY = '{"errorMessage": "Provided API key could not be found", "apikey": "sk-leaked"}'


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any = None,
        text: str = "",
        reason: str = "Bad Request",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.reason = reason

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Returns queued responses (or raises queued exceptions) in order."""

    def __init__(self, *responses: Any) -> None:
        self.queue = list(responses)
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kwargs: Any) -> Any:
        self.calls.append((method, url))
        item = self.queue.pop(0) if self.queue else FakeResponse(500, text="exhausted")
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def iam_calls(self) -> int:
        return sum(1 for _, url in self.calls if "iam.cloud.ibm.com" in url)

    @property
    def generation_calls(self) -> int:
        return sum(1 for _, url in self.calls if "/ml/v1/text/generation" in url)


def token_response(expires_in: int = 3600) -> FakeResponse:
    return FakeResponse(200, {"access_token": "tok-abc", "expires_in": expires_in})


def generation_response(text: str = "  Generated answer.  ") -> FakeResponse:
    return FakeResponse(200, {"results": [{"generated_text": text}]})


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> WatsonxSettings:
    monkeypatch.setenv("WATSONX_API_KEY", "real-api-key")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "real-project-id")
    monkeypatch.setenv("WATSONX_BACKOFF_FACTOR", "0")
    return WatsonxSettings()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast."""
    monkeypatch.setattr("portpulse.integrations.watsonx.time.sleep", lambda _seconds: None)


# ── Configuration gating ─────────────────────────────────────────────────────


def test_unconfigured_client_reports_disabled_and_refuses_to_call() -> None:
    client = WatsonxClient(WatsonxSettings(api_key=None, project_id=None))
    assert client.enabled is False
    with pytest.raises(WatsonxNotConfiguredError, match="not configured"):
        client.generate_text("hello")


def test_placeholder_credentials_do_not_enable_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WATSONX_API_KEY", "your_api_key_here")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "your_project_id_here")
    assert WatsonxClient(WatsonxSettings()).enabled is False


# ── Happy path and token caching ─────────────────────────────────────────────


def test_generate_text_returns_stripped_output(credentials: WatsonxSettings) -> None:
    session = FakeSession(token_response(), generation_response())
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]
    assert client.generate_text("prompt") == "Generated answer."


def test_iam_token_is_reused_across_calls(credentials: WatsonxSettings) -> None:
    session = FakeSession(token_response(), generation_response(), generation_response())
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    client.generate_text("first")
    client.generate_text("second")

    assert session.iam_calls == 1
    assert session.generation_calls == 2


def test_token_is_refetched_once_the_buffer_makes_it_stale(
    credentials: WatsonxSettings,
) -> None:
    # expires_in below the 300s buffer means the token is immediately considered stale.
    session = FakeSession(
        token_response(expires_in=10),
        generation_response(),
        token_response(expires_in=10),
        generation_response(),
    )
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    client.generate_text("first")
    client.generate_text("second")

    assert session.iam_calls == 2


# ── Failure handling ─────────────────────────────────────────────────────────


def test_auth_failure_message_excludes_the_response_body(credentials: WatsonxSettings) -> None:
    session = FakeSession(
        FakeResponse(400, {"errorMessage": "Provided API key could not be found"}, text=SECRET_BODY)
    )
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxAuthError) as excinfo:
        client.generate_text("prompt")

    message = str(excinfo.value)
    assert "Provided API key could not be found" in message
    assert "sk-leaked" not in message


def test_client_errors_are_not_retried(credentials: WatsonxSettings) -> None:
    session = FakeSession(FakeResponse(401, {"message": "unauthorized"}))
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxAuthError):
        client.generate_text("prompt")

    assert session.iam_calls == 1


def test_transient_errors_are_retried_then_succeed(credentials: WatsonxSettings) -> None:
    session = FakeSession(
        FakeResponse(503, {"message": "unavailable"}),
        token_response(),
        generation_response(),
    )
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    assert client.generate_text("prompt") == "Generated answer."
    assert session.iam_calls == 2


def test_network_errors_are_retried_up_to_the_limit(credentials: WatsonxSettings) -> None:
    session = FakeSession(*[requests.ConnectionError("no route")] * 3)
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxAuthError, match="Could not reach IBM IAM"):
        client.generate_text("prompt")

    assert session.iam_calls == credentials.max_retries


def test_auth_failure_opens_a_circuit_breaker(credentials: WatsonxSettings) -> None:
    session = FakeSession(FakeResponse(400, {"message": "bad key"}))
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxAuthError):
        client.generate_text("first")
    with pytest.raises(WatsonxAuthError, match="cooldown"):
        client.generate_text("second")

    assert session.iam_calls == 1, "the breaker must prevent a second IAM round trip"


def test_reset_cache_closes_the_circuit_breaker(credentials: WatsonxSettings) -> None:
    session = FakeSession(
        FakeResponse(400, {"message": "bad key"}), token_response(), generation_response()
    )
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxAuthError):
        client.generate_text("first")
    client.reset_cache()

    assert client.generate_text("second") == "Generated answer."


def test_generation_http_error_raises_generation_error(credentials: WatsonxSettings) -> None:
    session = FakeSession(
        token_response(), FakeResponse(400, {"errors": [{"message": "model_id not found"}]})
    )
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxGenerationError, match="model_id not found"):
        client.generate_text("prompt")


@pytest.mark.parametrize(
    "payload",
    [{}, {"results": []}, {"results": [{}]}, None],
)
def test_unexpected_generation_payload_raises_generation_error(
    credentials: WatsonxSettings, payload: Any
) -> None:
    session = FakeSession(token_response(), FakeResponse(200, payload, text="junk"))
    client = WatsonxClient(credentials, session=session)  # type: ignore[arg-type]

    with pytest.raises(WatsonxGenerationError, match="Unexpected response payload"):
        client.generate_text("prompt")


# ── Shared instance ──────────────────────────────────────────────────────────


def test_shared_client_is_cached_until_reset() -> None:
    first = get_client()
    assert get_client() is first
    reset_client_cache()
    assert get_client() is not first
