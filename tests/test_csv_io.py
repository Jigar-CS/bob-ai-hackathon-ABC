"""CSV parsing, validation and serialisation."""

from __future__ import annotations

from pathlib import Path

import pytest

from portpulse.constants import VESSEL_COLUMNS
from portpulse.csv_io import (
    decode_upload,
    parse_csv_text,
    read_csv_file,
    rows_to_csv,
    table_to_csv,
)
from portpulse.errors import CsvValidationError, DataFileError


def test_read_csv_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "berths.csv"
    path.write_text("berth_id,capacity_teu\nB1,16000\n", encoding="utf-8")
    assert read_csv_file(path) == [{"berth_id": "B1", "capacity_teu": "16000"}]


def test_read_csv_file_tolerates_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "berths.csv"
    path.write_text("berth_id,capacity_teu\nB1,16000\n", encoding="utf-8-sig")
    assert read_csv_file(path)[0]["berth_id"] == "B1"


def test_read_csv_file_missing_raises_data_file_error(tmp_path: Path) -> None:
    with pytest.raises(DataFileError, match="not found"):
        read_csv_file(tmp_path / "absent.csv")


def test_parse_csv_text_reports_every_missing_column() -> None:
    with pytest.raises(CsvValidationError, match="cargo_type, eta, priority, size_teu"):
        parse_csv_text("vessel_id,name\nV1,Alpha\n", VESSEL_COLUMNS)


def test_parse_csv_text_rejects_header_only_file() -> None:
    header = ",".join(VESSEL_COLUMNS) + "\n"
    with pytest.raises(CsvValidationError, match="no data rows"):
        parse_csv_text(header, VESSEL_COLUMNS)


def test_parse_csv_text_rejects_empty_input() -> None:
    with pytest.raises(CsvValidationError, match="empty or missing a header"):
        parse_csv_text("", VESSEL_COLUMNS)


def test_parse_csv_text_strips_header_whitespace() -> None:
    content = (
        " vessel_id , name , eta , size_teu , cargo_type , priority \nV1,A,2026-10-01 08:00,1,x,1\n"
    )
    rows = parse_csv_text(content, VESSEL_COLUMNS)
    assert rows[0]["vessel_id"] == "V1"


def test_decode_upload_rejects_non_utf8() -> None:
    with pytest.raises(CsvValidationError, match="not valid UTF-8"):
        decode_upload(b"\xff\xfe\x00vessel")


def test_decode_upload_strips_bom() -> None:
    assert decode_upload(b"\xef\xbb\xbfvessel_id") == "vessel_id"


def test_rows_to_csv_restricts_and_orders_columns() -> None:
    rows = [{"b": "2", "a": "1", "extra": "drop"}]
    assert rows_to_csv(rows, ("a", "b")).splitlines() == ["a,b", "1,2"]


def test_rows_to_csv_of_empty_input_is_empty() -> None:
    assert rows_to_csv([]) == ""


def test_table_to_csv_writes_header_and_rows() -> None:
    assert table_to_csv(("x", "y"), [[1, 2], [3, 4]]).splitlines() == ["x,y", "1,2", "3,4"]
