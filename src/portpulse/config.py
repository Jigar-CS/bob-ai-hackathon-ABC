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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from portpulse.constants import (
    ALTERNATE_PORTS_FILENAME,
    BERTHS_FILENAME,
    VESSELS_FILENAME,
)

PACKAGE_DIR: Path = Path(__file__).resolve().parent
STATIC_DIR: Path = PACKAGE_DIR / "static"
DEFAULT_DATA_DIR: Path = PACKAGE_DIR / "data"

#: Values that look like an untouched ``.env.example`` entry are treated as unset.
_PLACEHOLDER_MARKERS = ("your_", "_here", "changeme", "<", "xxx")

_ENV_FILE_CONFIG = SettingsConfigDict(
    env_file=".env",
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
    """IBM watsonx.ai connection settings (``WATSONX_*`` environment variables)."""

    model_config = SettingsConfigDict(env_prefix="WATSONX_", **_ENV_FILE_CONFIG)

    api_key: str | None = None
    project_id: str | None = None
    url: str = "https://us-south.ml.cloud.ibm.com"
    model_id: str = "ibm/granite-3-8b-instruct"
    api_version: str = "2024-05-01"
    iam_url: str = "https://iam.cloud.ibm.com/identity/token"

    iam_timeout_seconds: float = Field(default=10.0, gt=0)
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=1, le=10)
    backoff_factor: float = Field(default=0.5, ge=0)
    max_new_tokens: int = Field(default=300, ge=1, le=4096)

    #: Seconds to short-circuit token requests after an authentication failure.
    auth_cooldown_seconds: float = Field(default=60.0, ge=0)
    #: Renew tokens this many seconds before the IAM-reported expiry.
    token_expiry_buffer_seconds: int = Field(default=300, ge=0)

    @field_validator("api_key", "project_id", mode="before")
    @classmethod
    def _clean_credentials(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

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

    # ── Routing / LLM fan-out guards ─────────────────────────────────────────
    routing_max_workers: int = Field(default=8, ge=1, le=32)
    #: Hard ceiling on LLM calls per request; beyond this, template text is used.
    routing_max_llm_calls: int = Field(default=25, ge=0)

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
