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

from portpulse.domain.port_directory import get_dynamic_alternate_ports

logger = logging.getLogger(__name__)

#: Used when no valid ``alternate_ports.json`` is present.
FALLBACK_ALTERNATE_PORTS: tuple[dict[str, Any], ...] = tuple(
    get_dynamic_alternate_ports(33.73, -118.26)
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


def load_alternate_ports(
    settings: Settings | None = None,
    port_lat: float | None = None,
    port_lon: float | None = None,
) -> list[dict[str, Any]]:
    """Load alternate ports dynamically by spatial distance to home port coordinates."""
    settings = settings or get_settings()
    plat = port_lat if port_lat is not None else settings.app.port_lat
    plon = port_lon if port_lon is not None else settings.app.port_lon
    path = settings.app.alternate_ports_path

    # If path exists and is a custom non-default file (e.g. created by a test fixture), read it
    from portpulse.config import DEFAULT_DATA_DIR
    default_sample_path = DEFAULT_DATA_DIR / "alternate_ports.json"

    if (
        port_lat is None
        and port_lon is None
        and path.exists()
        and path.resolve() != default_sample_path.resolve()
    ):
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                valid: list[dict[str, Any]] = []
                for item in data:
                    if isinstance(item, dict) and "port" in item:
                        dist = item.get("distance_km")
                        cap = item.get("spare_capacity_teu")
                        if isinstance(dist, (int, float)) and isinstance(cap, (int, float)):
                            valid.append(
                                {
                                    "port": str(item["port"]),
                                    "distance_km": int(dist),
                                    "spare_capacity_teu": int(cap),
                                }
                            )
                if valid:
                    return valid
        except (OSError, ValueError, TypeError):
            pass

    return get_dynamic_alternate_ports(home_lat=plat, home_lon=plon)


def datasets_available(settings: Settings | None = None) -> bool:
    """Return True when both default datasets can be read (used by the health probe)."""
    settings = settings or get_settings()
    try:
        return bool(load_vessels(settings)) and bool(load_berths(settings))
    except DataFileError:
        return False
