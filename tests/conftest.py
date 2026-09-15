"""Shared pytest fixtures.

Two invariants the whole suite relies on:

1. No test reads developer environment variables or a local ``.env``; every test
   starts from a known configuration.
2. No test makes a network call. watsonx.ai credentials are explicitly blanked,
   so the routing engine takes its template-text path unless a test injects a
   fake client.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from portpulse.app import create_app
from portpulse.config import Settings, get_settings, reset_settings_cache
from portpulse.constants import BERTH_COLUMNS, VESSEL_COLUMNS
from portpulse.integrations.watsonx import reset_client_cache

VESSEL_CSV = (
    "vessel_id,name,eta,size_teu,cargo_type,priority\n"
    "V001,MV Alpha,2026-10-01 08:00,5000,reefer,1\n"
    "V002,MV Bravo,2026-10-01 14:00,7000,general,2\n"
    "V003,MV Charlie,2026-10-02 10:00,9000,hazmat,3\n"
)

BERTH_CSV = "berth_id,capacity_teu,crane_count,avg_dwell_hours\nB1,16000,4,6.0\nB2,12000,3,8.0\n"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test a clean, offline configuration."""
    for key in list(os.environ):
        if key.startswith(("PORTPULSE_", "WATSONX_", "BOB_", "AGENT_")):
            monkeypatch.delenv(key, raising=False)

    # Explicitly blank so a developer's .env cannot enable live API calls.
    monkeypatch.setenv("WATSONX_API_KEY", "")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "")
    monkeypatch.setenv("BOB_AGENT_API_KEY", "")
    monkeypatch.setenv("BOB_AGENT_PROJECT_ID", "")
    monkeypatch.setenv("PORTPULSE_ENVIRONMENT", "development")
    monkeypatch.setenv("PORTPULSE_LOG_LEVEL", "WARNING")

    reset_settings_cache()
    reset_client_cache()
    yield
    reset_settings_cache()
    reset_client_cache()


@pytest.fixture
def vessel_rows() -> list[dict[str, str]]:
    """Three vessels spanning two 24-hour windows."""
    return [
        {
            "vessel_id": "V001",
            "name": "MV Alpha",
            "eta": "2026-10-01 08:00",
            "size_teu": "5000",
            "cargo_type": "reefer",
            "priority": "1",
        },
        {
            "vessel_id": "V002",
            "name": "MV Bravo",
            "eta": "2026-10-01 14:00",
            "size_teu": "7000",
            "cargo_type": "general",
            "priority": "2",
        },
        {
            "vessel_id": "V003",
            "name": "MV Charlie",
            "eta": "2026-10-02 10:00",
            "size_teu": "9000",
            "cargo_type": "hazmat",
            "priority": "3",
        },
    ]


@pytest.fixture
def berth_rows() -> list[dict[str, str]]:
    """Two berths totalling 28,000 TEU of capacity."""
    return [
        {"berth_id": "B1", "capacity_teu": "16000", "crane_count": "4", "avg_dwell_hours": "6.0"},
        {"berth_id": "B2", "capacity_teu": "12000", "crane_count": "3", "avg_dwell_hours": "8.0"},
    ]


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary dataset directory, so tests never depend on shipped sample data."""
    directory = tmp_path / "data"
    directory.mkdir()
    (directory / "vessels.csv").write_text(VESSEL_CSV, encoding="utf-8")
    (directory / "berths.csv").write_text(BERTH_CSV, encoding="utf-8")
    monkeypatch.setenv("PORTPULSE_DATA_DIR", str(directory))
    reset_settings_cache()
    return directory


@pytest.fixture
def empty_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A dataset directory with no files, to exercise the 503 paths."""
    directory = tmp_path / "empty"
    directory.mkdir()
    monkeypatch.setenv("PORTPULSE_DATA_DIR", str(directory))
    reset_settings_cache()
    return directory


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return get_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """HTTP client with application lifespan (and startup checks) executed."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def required_columns() -> dict[str, tuple[str, ...]]:
    return {"vessels": VESSEL_COLUMNS, "berths": BERTH_COLUMNS}
