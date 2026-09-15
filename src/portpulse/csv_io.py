"""CSV reading, validation and serialisation helpers.

All functions here raise :mod:`portpulse.errors` exceptions rather than
``HTTPException`` so they can be reused outside a request context.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from portpulse.errors import CsvValidationError, DataFileError

logger = logging.getLogger(__name__)

Row = dict[str, str]


def read_csv_file(path: Path) -> list[Row]:
    """Read a CSV file from disk into a list of row dicts.

    Raises:
        DataFileError: if the file is missing or cannot be read/decoded.
    """
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError as err:
        raise DataFileError(f"Dataset not found: {path.name}") from err
    except (OSError, UnicodeDecodeError) as err:
        raise DataFileError(f"Could not read dataset {path.name}: {err}") from err


COLUMN_ALIASES: dict[str, str] = {
    # Vessel column aliases
    "vesselid": "vessel_id",
    "vessel_id": "vessel_id",
    "vessel": "vessel_id",
    "vessel_name": "name",
    "vesselname": "name",
    "name": "name",
    "ship_name": "name",
    "eta": "eta",
    "arrival": "eta",
    "arrival_time": "eta",
    "estimated_arrival": "eta",
    "size_teu": "size_teu",
    "sizeteu": "size_teu",
    "teu": "size_teu",
    "size": "size_teu",
    "cargo_type": "cargo_type",
    "cargotype": "cargo_type",
    "cargo": "cargo_type",
    "priority": "priority",
    "prio": "priority",
    "priority_level": "priority",
    # Berth column aliases
    "berth_id": "berth_id",
    "berthid": "berth_id",
    "berth": "berth_id",
    "capacity_teu": "capacity_teu",
    "capacityteu": "capacity_teu",
    "max_teu": "capacity_teu",
    "capacity": "capacity_teu",
    "crane_count": "crane_count",
    "cranecount": "crane_count",
    "cranes": "crane_count",
    "crane": "crane_count",
    "avg_dwell_hours": "avg_dwell_hours",
    "avgdwellhours": "avg_dwell_hours",
    "dwell_hours": "avg_dwell_hours",
    "dwell": "avg_dwell_hours",
    "avg_dwell": "avg_dwell_hours",
}


def normalize_column_name(col: str) -> str:
    cleaned = col.strip().lower()
    return COLUMN_ALIASES.get(cleaned, cleaned)


def parse_eta(val: object) -> datetime:
    """Parse ETA strings in various standard formats into a datetime object."""
    from portpulse.constants import ETA_FORMAT

    if not val:
        raise ValueError("ETA string is empty")

    cleaned_str = str(val).strip()
    raw = cleaned_str.rstrip("Zz").replace("T", " ")
    for fmt in (
        ETA_FORMAT,
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        iso_str = cleaned_str[:-1] + "+00:00" if cleaned_str.endswith(("Z", "z")) else cleaned_str
        return datetime.fromisoformat(iso_str)
    except ValueError as err:
        raise ValueError(f"Unparseable ETA format: {val}") from err


def decode_upload(raw: bytes) -> str:
    """Decode uploaded bytes as UTF-8, tolerating a BOM.

    Raises:
        CsvValidationError: if the payload is not valid UTF-8.
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        raise CsvValidationError(
            "File is not valid UTF-8 text. Re-export the CSV using UTF-8 encoding."
        ) from err


def parse_csv_text(content: str, required_columns: Iterable[str]) -> list[Row]:
    """Parse CSV text and assert the required columns are present.

    Raises:
        CsvValidationError: on empty input, missing headers or missing columns.
    """
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise CsvValidationError("CSV file is empty or missing a header row.")

    column_mapping = {col: normalize_column_name(col) for col in reader.fieldnames if col}
    normalized_headers = set(column_mapping.values())
    missing = sorted(set(required_columns) - normalized_headers)
    if missing:
        raise CsvValidationError(f"CSV missing required columns: {', '.join(missing)}")

    try:
        rows = [
            {
                column_mapping[k]: (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k and k in column_mapping
            }
            for row in reader
        ]
    except csv.Error as err:
        raise CsvValidationError(f"Malformed CSV content: {err}") from err

    if not rows:
        raise CsvValidationError("CSV file contains no data rows.")
    return rows


def _sanitize_csv_cell(value: object) -> object:
    """Escape values starting with =, +, -, @ to prevent spreadsheet formula injection."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def rows_to_csv(rows: Sequence[Row], fieldnames: Sequence[str] | None = None) -> str:
    """Serialise row dicts back to CSV text."""
    if not rows:
        return ""
    columns = list(fieldnames) if fieldnames else list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    sanitized_rows = [{k: str(_sanitize_csv_cell(v)) for k, v in row.items()} for row in rows]
    writer.writerows(sanitized_rows)
    return buffer.getvalue()


def table_to_csv(header: Sequence[str], records: Iterable[Sequence[object]]) -> str:
    """Serialise a positional table (header + rows) to CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for record in records:
        sanitized_row = [_sanitize_csv_cell(cell) for cell in record]
        writer.writerow(sanitized_row)
    return buffer.getvalue()
