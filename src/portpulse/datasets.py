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
from portpulse.domain.port_directory import get_dynamic_alternate_ports
from portpulse.errors import DataFileError

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


ORIGIN_CATALOG: dict[str, tuple[str, float, float]] = {
    "shanghai": ("Shanghai Port", 31.23, 121.47),
    "pearl": ("Guangzhou Port", 23.09, 113.48),
    "hong kong": ("Hong Kong Port", 22.31, 114.16),
    "tokyo": ("Port of Tokyo", 35.68, 139.69),
    "yokohama": ("Port of Yokohama", 35.44, 139.64),
    "formosa": ("Port of Kaohsiung", 22.62, 120.28),
    "singapore": ("Port of Singapore", 1.29, 103.85),
    "korea": ("Port of Busan", 35.10, 129.04),
    "busan": ("Port of Busan", 35.10, 129.04),
    "dragon": ("Shanghai Port", 31.23, 121.47),
    "yellow sea": ("Qingdao Port", 36.07, 120.38),
    "qingdao": ("Qingdao Port", 36.07, 120.38),
    "pacific": ("Ningbo-Zhoushan Port", 29.87, 121.55),
    "ningbo": ("Ningbo-Zhoushan Port", 29.87, 121.55),
    "columbia": ("Port of Vancouver", 49.28, -123.12),
    "golden state": ("Port of LA / Long Beach", 33.73, -118.26),
    "silk": ("Jebel Ali Port (Dubai)", 25.27, 55.29),
    "dubai": ("Jebel Ali Port (Dubai)", 25.27, 55.29),
    "ocean": ("Port of Yokohama", 35.44, 139.64),
}

FALLBACK_ORIGINS = [
    ("Shanghai Port", 31.23, 121.47),
    ("Hong Kong Port", 22.31, 114.16),
    ("Port of Yokohama", 35.44, 139.64),
    ("Port of Singapore", 1.29, 103.85),
    ("Port of Busan", 35.10, 129.04),
    ("Ningbo-Zhoushan Port", 29.87, 121.55),
    ("Qingdao Port", 36.07, 120.38),
    ("Jebel Ali Port (Dubai)", 25.27, 55.29),
    ("Port of Rotterdam", 51.92, 4.48),
    ("Port of LA / Long Beach", 33.73, -118.26),
]


def enrich_vessel_rows(rows: list[Row]) -> list[Row]:
    """Enrich vessel rows with origin_port, origin_lat, and origin_lon if missing."""
    enriched: list[Row] = []
    for idx, r in enumerate(rows):
        v = dict(r)
        has_orig = (
            v.get("origin_port")
            and v.get("origin_lat") is not None
            and v.get("origin_lon") is not None
            and str(v.get("origin_lat")).strip() != ""
            and str(v.get("origin_lon")).strip() != ""
        )
        if not has_orig:
            v_name = (v.get("name") or v.get("vessel_name") or v.get("vessel_id") or "").lower()
            matched = False
            for kw, (p_name, lat, lon) in ORIGIN_CATALOG.items():
                if kw in v_name:
                    v["origin_port"] = p_name
                    v["origin_lat"] = str(lat)
                    v["origin_lon"] = str(lon)
                    matched = True
                    break
            if not matched:
                fb_name, fb_lat, fb_lon = FALLBACK_ORIGINS[idx % len(FALLBACK_ORIGINS)]
                v["origin_port"] = fb_name
                v["origin_lat"] = str(fb_lat)
                v["origin_lon"] = str(fb_lon)
        enriched.append(v)
    return enriched


def load_vessels(settings: Settings | None = None) -> list[Row]:
    """Load the default vessel schedule.

    Raises:
        DataFileError: if the dataset is missing or unreadable.
    """
    settings = settings or get_settings()
    rows = read_csv_file(settings.app.vessels_path)
    return enrich_vessel_rows(rows)


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
