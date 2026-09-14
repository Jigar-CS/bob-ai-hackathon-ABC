"""Dataset loading, including the alternate-port catalogue fallbacks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portpulse.datasets import (
    FALLBACK_ALTERNATE_PORTS,
    datasets_available,
    load_alternate_ports,
    load_berths,
    load_vessels,
)
from portpulse.errors import DataFileError


def test_default_datasets_load(settings) -> None:
    assert len(load_vessels(settings)) == 3
    assert len(load_berths(settings)) == 2
    assert datasets_available(settings) is True


def test_missing_datasets_raise_and_are_reported_unavailable(
    empty_data_dir: Path,
) -> None:
    from portpulse.config import get_settings

    settings = get_settings()
    with pytest.raises(DataFileError):
        load_vessels(settings)
    assert datasets_available(settings) is False


def test_catalogue_is_read_from_disk(settings, data_dir: Path) -> None:
    (data_dir / "alternate_ports.json").write_text(
        json.dumps([{"port": "Port of Lisbon", "distance_km": 12, "spare_capacity_teu": 3000}]),
        encoding="utf-8",
    )
    assert load_alternate_ports(settings) == [
        {"port": "Port of Lisbon", "distance_km": 12, "spare_capacity_teu": 3000}
    ]


def test_missing_catalogue_falls_back_to_demo_ports(settings) -> None:
    assert load_alternate_ports(settings) == [dict(port) for port in FALLBACK_ALTERNATE_PORTS]


@pytest.mark.parametrize(
    "content",
    ["not json at all", "{}", "[]", '"a string"'],
)
def test_unusable_catalogue_falls_back_to_demo_ports(
    settings,
    data_dir: Path,
    content: str,
) -> None:
    (data_dir / "alternate_ports.json").write_text(content, encoding="utf-8")
    assert load_alternate_ports(settings) == [dict(port) for port in FALLBACK_ALTERNATE_PORTS]


def test_malformed_entries_are_skipped_but_good_ones_kept(
    settings,
    data_dir: Path,
) -> None:
    (data_dir / "alternate_ports.json").write_text(
        json.dumps(
            [
                "not-an-object",
                {"port": "Missing distance"},
                {"port": "Bad number", "distance_km": "far", "spare_capacity_teu": 1},
                {"port": "Port of Vigo", "distance_km": 300, "spare_capacity_teu": 5000},
            ]
        ),
        encoding="utf-8",
    )
    assert load_alternate_ports(settings) == [
        {"port": "Port of Vigo", "distance_km": 300, "spare_capacity_teu": 5000}
    ]


def test_entirely_malformed_catalogue_falls_back(
    settings,
    data_dir: Path,
) -> None:
    (data_dir / "alternate_ports.json").write_text(
        json.dumps([{"port": "Only a name"}]), encoding="utf-8"
    )
    assert load_alternate_ports(settings) == [dict(port) for port in FALLBACK_ALTERNATE_PORTS]
