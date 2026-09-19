"""Typed application configuration.

Every tunable value lives here rather than as a literal buried in a module,
so behaviour can be changed per environment without a code change.

Two independent env namespaces are used:

* ``PORTPULSE_*`` — application behaviour (logging, CORS, limits, thresholds)
* ``WATSONX_*``   — IBM watsonx.ai credentials and endpoint tuning

Settings are read once and cached. Tests call :func:`reset_settings_cache`
after mutating the environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from portpulse.constants import (
    ALTERNATE_PORTS_FILENAME,
    BERTHS_FILENAME,
    VESSELS_FILENAME,
)

PACKAGE_DIR: Path = Path(__file__).resolve().parent
STATIC_DIR: Path = PACKAGE_DIR / "static"
DEFAULT_DATA_DIR: Path = PACKAGE_DIR / "data"

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parent.parent.parent
    for _p in (_root / ".env", _root / "src" / ".env", Path(".env"), Path("src/.env")):
        if _p.is_file():
            load_dotenv(_p, override=True)
except ImportError:
    pass

#: Values that look like an untouched ``.env.example`` entry are treated as unset.
_PLACEHOLDER_MARKERS = ("your_", "_here", "changeme", "<", "xxx")

_ENV_FILE_CONFIG = SettingsConfigDict(
    env_file=(".env", "src/.env", "../.env"),
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
)


def _blank_to_none(value: str | None) -> str | None:
    """Normalise placeholder / empty credential strings to ``None``."""
    if value is None:
        return None
    cleaned = value.strip().strip("\"'")
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        return None
    return cleaned


class WatsonxSettings(BaseSettings):
    """IBM watsonx.ai / BOB Agent connection settings.

    Supports ``WATSONX_*`` or ``BOB_AGENT_*`` environment variables.
    """

    model_config = _ENV_FILE_CONFIG

    api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WATSONX_API_KEY", "BOB_AGENT_API_KEY", "BOB_API_KEY", "AGENT_API_KEY"
        ),
    )
    project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "WATSONX_PROJECT_ID", "BOB_AGENT_PROJECT_ID", "BOB_PROJECT_ID"
        ),
    )
    url: str = Field(
        default="https://us-south.ml.cloud.ibm.com",
        validation_alias=AliasChoices("WATSONX_URL", "BOB_AGENT_URL"),
    )
    model_id: str = Field(
        default="ibm/granite-3-8b-instruct",
        validation_alias=AliasChoices("WATSONX_MODEL_ID", "BOB_AGENT_MODEL_ID"),
    )
    api_version: str = Field(
        default="2024-05-01",
        validation_alias=AliasChoices("WATSONX_API_VERSION", "BOB_AGENT_API_VERSION"),
    )
    iam_url: str = Field(
        default="https://iam.cloud.ibm.com/identity/token",
        validation_alias=AliasChoices("WATSONX_IAM_URL", "BOB_AGENT_IAM_URL"),
    )

    iam_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        validation_alias=AliasChoices(
            "WATSONX_IAM_TIMEOUT_SECONDS", "BOB_AGENT_IAM_TIMEOUT_SECONDS"
        ),
    )
    request_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        validation_alias=AliasChoices(
            "WATSONX_REQUEST_TIMEOUT_SECONDS", "BOB_AGENT_REQUEST_TIMEOUT_SECONDS"
        ),
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        validation_alias=AliasChoices("WATSONX_MAX_RETRIES", "BOB_AGENT_MAX_RETRIES"),
    )
    backoff_factor: float = Field(
        default=0.5,
        ge=0,
        validation_alias=AliasChoices("WATSONX_BACKOFF_FACTOR", "BOB_AGENT_BACKOFF_FACTOR"),
    )
    max_new_tokens: int = Field(
        default=300,
        ge=1,
        le=4096,
        validation_alias=AliasChoices("WATSONX_MAX_NEW_TOKENS", "BOB_AGENT_MAX_NEW_TOKENS"),
    )

    #: Seconds to short-circuit token requests after an authentication failure.
    auth_cooldown_seconds: float = Field(
        default=60.0,
        ge=0,
        validation_alias=AliasChoices(
            "WATSONX_AUTH_COOLDOWN_SECONDS", "BOB_AGENT_AUTH_COOLDOWN_SECONDS"
        ),
    )
    #: Renew tokens this many seconds before the IAM-reported expiry.
    token_expiry_buffer_seconds: int = Field(
        default=300,
        ge=0,
        validation_alias=AliasChoices(
            "WATSONX_TOKEN_EXPIRY_BUFFER_SECONDS", "BOB_AGENT_TOKEN_EXPIRY_BUFFER_SECONDS"
        ),
    )

    @field_validator("api_key", "project_id", mode="before")
    @classmethod
    def _clean_credentials(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _fallback_bob_agent_keys(self) -> WatsonxSettings:
        import os

        if not self.api_key:
            for key in ("BOB_AGENT_API_KEY", "BOB_API_KEY", "AGENT_API_KEY"):
                val = _blank_to_none(os.getenv(key))
                if val:
                    object.__setattr__(self, "api_key", val)
                    break

        if self.api_key and not self.project_id:
            for key in ("BOB_AGENT_PROJECT_ID", "BOB_PROJECT_ID", "WATSONX_PROJECT_ID"):
                val = _blank_to_none(os.getenv(key))
                if val:
                    object.__setattr__(self, "project_id", val)
                    break
            if not self.project_id:
                object.__setattr__(self, "project_id", "bob-agent-project")
        return self

    @field_validator("url", "iam_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def enabled(self) -> bool:
        """True when real credentials are present, so LLM calls are worth attempting."""
        return bool(self.api_key and self.project_id)

    @property
    def generation_endpoint(self) -> str:
        return f"{self.url}/ml/v1/text/generation?version={self.api_version}"


class AppSettings(BaseSettings):
    """Application behaviour settings (``PORTPULSE_*`` environment variables)."""

    model_config = SettingsConfigDict(env_prefix="PORTPULSE_", **_ENV_FILE_CONFIG)

    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False
    ml_enabled: bool = False

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    #: Directory holding ``vessels.csv`` / ``berths.csv`` / ``alternate_ports.json``.
    data_dir: Path = DEFAULT_DATA_DIR

    #: Comma-separated list of allowed CORS origins. ``*`` is rejected in production.
    cors_allow_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    #: When set, state-changing endpoints require this value in the ``X-API-Key`` header.
    api_key: str | None = None

    max_upload_bytes: int = Field(default=5 * 1024 * 1024, gt=0)

    # ── Planning parameters ──────────────────────────────────────────────────
    #: A vessel queued longer than this is treated as unplaceable and rerouted.
    max_berth_wait_hours: float = Field(default=12.0, gt=0)
    congestion_high_risk_ratio: float = Field(default=0.9, gt=0)
    congestion_medium_risk_ratio: float = Field(default=0.6, gt=0)
    #: Baseline crane count assumed by berth CSV avg_dwell_hours.
    baseline_crane_count: int = Field(default=4, ge=1, le=50)
    crane_dwell_min_multiplier: float = Field(default=0.5, gt=0)
    crane_dwell_max_multiplier: float = Field(default=2.0, gt=0)

    # ── Routing / LLM fan-out guards ─────────────────────────────────────────
    routing_max_workers: int = Field(default=8, ge=1, le=32)
    #: Hard ceiling on LLM calls per request; beyond this, template text is used.
    routing_max_llm_calls: int = Field(default=25, ge=0)

    # ── Weather delay engine ──────────────────────────────────────────────────
    #: Enable real-time weather delay adjustment for vessel ETAs.
    weather_enabled: bool = True
    #: Default Home Port name.
    port_name: str = "JNPT / Nhava Sheva (Navi Mumbai)"
    #: Destination port latitude (used to fetch weather along vessel routes).
    port_lat: float = Field(default=18.95, ge=-90.0, le=90.0)
    #: Destination port longitude.
    port_lon: float = Field(default=72.95, ge=-180.0, le=180.0)
    #: HTTP timeout in seconds for weather API requests.
    weather_api_timeout_seconds: float = Field(default=5.0, gt=0)
    weather_max_workers: int = Field(default=8, ge=1, le=32)
    weather_max_vessels: int = Field(default=200, ge=1)

    @field_validator("api_key", mode="before")
    @classmethod
    def _clean_api_key(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def vessels_path(self) -> Path:
        return self.data_dir / VESSELS_FILENAME

    @property
    def berths_path(self) -> Path:
        return self.data_dir / BERTHS_FILENAME

    @property
    def alternate_ports_path(self) -> Path:
        return self.data_dir / ALTERNATE_PORTS_FILENAME


@dataclass(frozen=True)
class Settings:
    """Root settings object composing the two independent env namespaces.

    Deliberately a plain dataclass rather than a ``BaseSettings`` model: nesting
    settings models would make pydantic look for ``APP`` / ``WATSONX`` env vars
    and attempt to JSON-decode them.
    """

    app: AppSettings
    watsonx: WatsonxSettings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings(app=AppSettings(), watsonx=WatsonxSettings())


def reset_settings_cache() -> None:
    """Drop the cached settings so the next :func:`get_settings` re-reads the env."""
    get_settings.cache_clear()
