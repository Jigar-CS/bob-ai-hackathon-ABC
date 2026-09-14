"""Upload and template endpoints."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from portpulse.app import create_app
from portpulse.config import get_settings, reset_settings_cache
from portpulse.constants import BERTH_COLUMNS, VESSEL_COLUMNS

VESSEL_UPLOAD = (
    b"vessel_id,name,eta,size_teu,cargo_type,priority\n"
    b"V100,MV Uploaded,2026-11-01 08:00,4500,general,1\n"
)
BERTH_UPLOAD = b"berth_id,capacity_teu,crane_count,avg_dwell_hours\nB9,20000,5,10.0\n"


def upload(
    client: TestClient, dataset: str, content: bytes, filename: str = "data.csv"
) -> httpx.Response:
    return client.post(
        f"/api/v1/uploads/{dataset}",
        files={"file": (filename, content, "text/csv")},
    )


def test_uploaded_vessels_replace_the_default_schedule(client: TestClient) -> None:
    response = upload(client, "vessels", VESSEL_UPLOAD)

    assert response.status_code == 200
    assignments = response.json()["berth_assignments"]
    assert [record["vessel_id"] for record in assignments] == ["V100"]


def test_uploaded_berths_replace_the_default_capacity(client: TestClient) -> None:
    response = upload(client, "berths", BERTH_UPLOAD)

    assert response.status_code == 200
    assignments = response.json()["berth_assignments"]
    assert {record["berth_id"] for record in assignments} == {"B9"}


def test_non_csv_extension_is_rejected(client: TestClient) -> None:
    response = upload(client, "vessels", VESSEL_UPLOAD, filename="schedule.xlsx")
    assert response.status_code == 400
    assert "must have a .csv extension" in response.json()["detail"]


def test_missing_columns_are_listed_in_the_error(client: TestClient) -> None:
    response = upload(client, "vessels", b"vessel_id,name\nV1,Alpha\n")
    assert response.status_code == 400
    assert "CSV missing required columns" in response.json()["detail"]


def test_non_utf8_upload_is_a_client_error_not_a_crash(client: TestClient) -> None:
    response = upload(client, "vessels", b"vessel_id\n\xff\xfe\x00bad")
    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]


def test_oversized_upload_is_rejected_with_413(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORTPULSE_MAX_UPLOAD_BYTES", "128")
    reset_settings_cache()

    with TestClient(create_app(get_settings())) as client:
        response = upload(client, "vessels", VESSEL_UPLOAD + b"x" * 1024)

    assert response.status_code == 413
    assert "maximum upload size" in response.json()["detail"]


def test_unknown_dataset_name_is_rejected(client: TestClient) -> None:
    response = upload(client, "trucks", VESSEL_UPLOAD)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("dataset", "columns"),
    [("vessels", VESSEL_COLUMNS), ("berths", BERTH_COLUMNS)],
)
def test_templates_expose_exactly_the_required_columns(
    client: TestClient, dataset: str, columns: tuple[str, ...]
) -> None:
    response = client.get(f"/api/v1/templates/{dataset}")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert f'filename="sample_{dataset}.csv"' in response.headers["content-disposition"]
    assert response.text.splitlines()[0] == ",".join(columns)
