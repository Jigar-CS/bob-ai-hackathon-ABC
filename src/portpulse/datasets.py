"""Dataset access.

Wraps the on-disk CSV/JSON datasets behind small functions so the storage
mechanism can later be swapped for a database or a live port-scheduling API
without touching the domain or API layers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from portpulse.config import Settings, get_settings
from portpulse.csv_io import Row, read_csv_file
from portpulse.errors import DataFileError

logger = logging.getLogger(__name__)

#: Used when no ``alternate_ports.json`` is present. Illustrative demo data.
FALLBACK_ALTERNATE_PORTS: tuple[dict[str, Any], ...] = (
    {"port": "Port of Oakland", "distance_km": 620, "spare_capacity_teu": 9000},
    {"port": "Port of Tacoma", "distance_km": 1450, "spare_capacity_teu": 14000},
    {"port": "Port of Ensenada", "distance_km": 240, "spare_capacity_teu": 4000},
)


def ensure_sample_backups(settings: Settings | None = None) -> None:
    """Backup default bundled sample CSV datasets on first load if backups do not exist."""
    settings = settings or get_settings()
    sample_vessels = settings.app.data_dir / "vessels.sample.csv"
    sample_berths = settings.app.data_dir / "berths.sample.csv"

    if not sample_vessels.exists() and settings.app.vessels_path.exists():
        try:
            sample_vessels.write_bytes(settings.app.vessels_path.read_bytes())
        except OSError as err:
            logger.debug("Could not write sample vessels backup: %s", err)

    if not sample_berths.exists() and settings.app.berths_path.exists():
        try:
            sample_berths.write_bytes(settings.app.berths_path.read_bytes())
        except OSError as err:
            logger.debug("Could not write sample berths backup: %s", err)


def reset_default_datasets(settings: Settings | None = None) -> None:
    """Reset vessel schedule and berth capacity tables back to default sample data."""
    settings = settings or get_settings()
    sample_vessels = settings.app.data_dir / "vessels.sample.csv"
    sample_berths = settings.app.data_dir / "berths.sample.csv"

    if sample_vessels.exists():
        settings.app.vessels_path.write_bytes(sample_vessels.read_bytes())
    if sample_berths.exists():
        settings.app.berths_path.write_bytes(sample_berths.read_bytes())


def load_vessels(settings: Settings | None = None) -> list[Row]:
    """Load the default vessel schedule.

    Raises:
        DataFileError: if the dataset is missing or unreadable.
    """
    settings = settings or get_settings()
    return read_csv_file(settings.app.vessels_path)


def load_berths(settings: Settings | None = None) -> list[Row]:
    """Load the default berth capacity table.

    Raises:
        DataFileError: if the dataset is missing or unreadable.
    """
    settings = settings or get_settings()
    return read_csv_file(settings.app.berths_path)


def load_alternate_ports(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Load the alternate-port catalogue, falling back to built-in demo data."""
    settings = settings or get_settings()
    path = settings.app.alternate_ports_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("No alternate port catalogue at %s — using built-in demo list.", path)
        return [dict(port) for port in FALLBACK_ALTERNATE_PORTS]
    except (OSError, json.JSONDecodeError) as err:
        logger.error("Could not parse %s (%s) — using built-in demo list.", path, err)
        return [dict(port) for port in FALLBACK_ALTERNATE_PORTS]

    if not isinstance(raw, list) or not raw:
        logger.error("%s must contain a non-empty JSON array — using built-in demo list.", path)
        return [dict(port) for port in FALLBACK_ALTERNATE_PORTS]

    ports: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            logger.warning("Skipping non-object entry in %s: %r", path.name, entry)
            continue
        try:
            ports.append(
                {
                    "port": str(entry["port"]),
                    "distance_km": int(entry["distance_km"]),
                    "spare_capacity_teu": int(entry["spare_capacity_teu"]),
                }
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Skipping malformed port entry in %s: %r (%s)", path.name, entry, err)

    if not ports:
        logger.error("No usable entries in %s — using built-in demo list.", path)
        return [dict(port) for port in FALLBACK_ALTERNATE_PORTS]
    return ports


def datasets_available(settings: Settings | None = None) -> bool:
    """Return True when both default datasets can be read (used by the health probe)."""
    settings = settings or get_settings()
    try:
        return bool(load_vessels(settings)) and bool(load_berths(settings))
    except DataFileError:
        return False
