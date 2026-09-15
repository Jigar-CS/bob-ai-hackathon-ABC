"""CSV reading, validation and serialisation helpers.

All functions here raise :mod:`portpulse.errors` exceptions rather than
``HTTPException`` so they can be reused outside a request context.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Iterable, Sequence
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

    headers = {column.strip() for column in reader.fieldnames if column}
    missing = sorted(set(required_columns) - headers)
    if missing:
        raise CsvValidationError(f"CSV missing required columns: {', '.join(missing)}")

    try:
        rows = [{(k.strip() if k else k): v for k, v in row.items()} for row in reader]
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
