"""Dataset upload and template-download endpoints.

Both datasets share one implementation; the only per-dataset difference is the
required column set and which side of the plan input it replaces.
"""

from __future__ import annotations

import contextlib
import logging
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from portpulse.config import Settings, get_settings
from portpulse.constants import BERTH_COLUMNS, VESSEL_COLUMNS
from portpulse.csv_io import Row, decode_upload, parse_csv_text, rows_to_csv
from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.planner import generate_ops_plan
from portpulse.schemas import ErrorResponse, OpsPlan
from portpulse.security import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["datasets"])

_UPLOAD_CHUNK_BYTES = 64 * 1024

#: Spelled out rather than taken from ``starlette.status``, whose name for this
#: code changed between releases.
HTTP_413_CONTENT_TOO_LARGE = 413


class DatasetName(str, Enum):
    """The two datasets a plan is built from."""

    vessels = "vessels"
    berths = "berths"


_REQUIRED_COLUMNS: dict[DatasetName, tuple[str, ...]] = {
    DatasetName.vessels: VESSEL_COLUMNS,
    DatasetName.berths: BERTH_COLUMNS,
}


async def _read_within_limit(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, aborting as soon as it exceeds ``max_bytes``.

    Streamed rather than buffered so an oversized upload cannot be fully
    materialised in memory before the limit is enforced.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            limit_mb = max(1, max_bytes // 1024 // 1024)
            raise HTTPException(
                status_code=HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"File exceeds the maximum upload size of {max_bytes:,} bytes (~{limit_mb} MB)."
                ),
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/uploads/both",
    response_model=OpsPlan,
    summary="Upload both vessels and berths CSV files together to regenerate the plan",
    dependencies=[Depends(require_api_key)],
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    },
)
async def upload_both_datasets(
    vessels_file: UploadFile = File(..., description="Compulsory UTF-8 Vessels CSV file"),
    berths_file: UploadFile = File(..., description="Compulsory UTF-8 Berths CSV file"),
    port_name: str | None = Form(None),
    port_lat: str | float | None = Form(None),
    port_lon: str | float | None = Form(None),
    settings: Settings = Depends(get_settings),
) -> OpsPlan:
    """Regenerate the plan using compulsory uploads for both vessel schedule and berth capacity."""
    for f_name, f_obj in (("vessels", vessels_file), ("berths", berths_file)):
        fn = f_obj.filename or ""
        if not fn.lower().endswith(".csv"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{f_name.capitalize()} file must have a .csv extension.",
            )

    from portpulse.constants import BERTH_OPTIONAL_COLUMNS, VESSEL_OPTIONAL_COLUMNS

    v_raw = await _read_within_limit(vessels_file, settings.app.max_upload_bytes)
    v_rows: list[Row] = parse_csv_text(decode_upload(v_raw), _REQUIRED_COLUMNS[DatasetName.vessels])
    v_cols = list(_REQUIRED_COLUMNS[DatasetName.vessels])
    if v_rows:
        for opt_col in VESSEL_OPTIONAL_COLUMNS:
            if opt_col in v_rows[0] and opt_col not in v_cols:
                v_cols.append(opt_col)
    settings.app.vessels_path.write_text(rows_to_csv(v_rows, tuple(v_cols)), encoding="utf-8")

    b_raw = await _read_within_limit(berths_file, settings.app.max_upload_bytes)
    b_rows: list[Row] = parse_csv_text(decode_upload(b_raw), _REQUIRED_COLUMNS[DatasetName.berths])
    b_cols = list(_REQUIRED_COLUMNS[DatasetName.berths])
    if b_rows:
        for opt_col in BERTH_OPTIONAL_COLUMNS:
            if opt_col in b_rows[0] and opt_col not in b_cols:
                b_cols.append(opt_col)
    settings.app.berths_path.write_text(rows_to_csv(b_rows, tuple(b_cols)), encoding="utf-8")

    if port_name and str(port_name).strip():
        settings.app.port_name = str(port_name).strip()
    if port_lat is not None and str(port_lat).strip():
        with contextlib.suppress(ValueError):
            settings.app.port_lat = float(port_lat)
    if port_lon is not None and str(port_lon).strip():
        with contextlib.suppress(ValueError):
            settings.app.port_lon = float(port_lon)

    logger.info(
        "Accepted combined upload: %d vessels, %d berths (Port: %s, lat=%s, lon=%s)",
        len(v_rows),
        len(b_rows),
        port_name or "Home Port",
        settings.app.port_lat,
        settings.app.port_lon,
    )

    return OpsPlan.model_validate(generate_ops_plan(load_vessels(settings), load_berths(settings)))


@router.post(
    "/uploads/{dataset}",
    response_model=OpsPlan,
    summary="Replace one dataset with an uploaded CSV and regenerate the plan",
    dependencies=[Depends(require_api_key)],
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
    },
)
async def upload_dataset(
    dataset: DatasetName,
    file: UploadFile = File(..., description="UTF-8 CSV file"),
    settings: Settings = Depends(get_settings),
) -> OpsPlan:
    """Regenerate the plan using an uploaded CSV for one side of the input."""
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a .csv extension.",
        )

    raw = await _read_within_limit(file, settings.app.max_upload_bytes)
    rows: list[Row] = parse_csv_text(decode_upload(raw), _REQUIRED_COLUMNS[dataset])
    logger.info("Accepted %s upload '%s' with %d rows", dataset.value, filename, len(rows))

    from portpulse.constants import BERTH_OPTIONAL_COLUMNS, VESSEL_OPTIONAL_COLUMNS

    target_path = (
        settings.app.vessels_path if dataset is DatasetName.vessels else settings.app.berths_path
    )
    cols = list(_REQUIRED_COLUMNS[dataset])
    if dataset is DatasetName.vessels and rows:
        for opt_col in VESSEL_OPTIONAL_COLUMNS:
            if opt_col in rows[0] and opt_col not in cols:
                cols.append(opt_col)
    elif dataset is DatasetName.berths and rows:
        for opt_col in BERTH_OPTIONAL_COLUMNS:
            if opt_col in rows[0] and opt_col not in cols:
                cols.append(opt_col)
    normalized_csv = rows_to_csv(rows, tuple(cols))
    target_path.write_text(normalized_csv, encoding="utf-8")

    return OpsPlan.model_validate(generate_ops_plan(load_vessels(settings), load_berths(settings)))


@router.post(
    "/datasets/reset",
    response_model=OpsPlan,
    summary="Reset datasets back to default sample data",
    dependencies=[Depends(require_api_key)],
)
def reset_datasets(settings: Settings = Depends(get_settings)) -> OpsPlan:
    """Restore original bundled vessel schedule and berth capacity tables."""
    from portpulse.datasets import reset_default_datasets

    reset_default_datasets(settings)
    return OpsPlan.model_validate(generate_ops_plan(load_vessels(settings), load_berths(settings)))


@router.get(
    "/templates/{dataset}",
    response_class=Response,
    summary="Download a sample CSV showing the expected columns",
    responses={200: {"content": {"text/csv": {}}, "description": "Sample CSV."}},
)
def download_template(
    dataset: DatasetName,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Return the bundled sample dataset as a starting point for uploads."""
    rows = load_vessels(settings) if dataset is DatasetName.vessels else load_berths(settings)
    columns = _REQUIRED_COLUMNS[dataset]
    return Response(
        content=rows_to_csv(rows, columns),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="sample_{dataset.value}.csv"',
        },
    )


@router.get(
    "/ports/directory",
    summary="Get global and Indian country-wise port directory with auto-coordinates",
)
def get_port_directory() -> dict[str, Any]:
    """Return country-grouped port directory with pre-configured coordinates."""
    from portpulse.domain.port_directory import PORT_DIRECTORY

    return PORT_DIRECTORY
