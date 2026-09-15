"""Dataset upload and template-download endpoints.

Both datasets share one implementation; the only per-dataset difference is the
required column set and which side of the plan input it replaces.
"""

from __future__ import annotations

import logging
from enum import Enum

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

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
    """Regenerate the plan using an uploaded CSV for one side of the input.

    The other side keeps using the default dataset, so an operator can iterate on
    a vessel schedule without re-uploading berth capacity.
    """
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a .csv extension.",
        )

    raw = await _read_within_limit(file, settings.app.max_upload_bytes)
    rows: list[Row] = parse_csv_text(decode_upload(raw), _REQUIRED_COLUMNS[dataset])
    logger.info("Accepted %s upload '%s' with %d rows", dataset.value, filename, len(rows))

    target_path = (
        settings.app.vessels_path if dataset is DatasetName.vessels else settings.app.berths_path
    )
    target_path.write_bytes(raw)

    return OpsPlan.model_validate(generate_ops_plan(load_vessels(settings), load_berths(settings)))


@router.post(
    "/datasets/reset",
    response_model=OpsPlan,
    summary="Reset datasets back to default sample data",
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
