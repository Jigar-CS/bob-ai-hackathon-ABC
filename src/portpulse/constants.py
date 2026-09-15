"""Shared constants for data contracts.

Kept in one place so the API layer, the domain layer and the sample-data
generator cannot drift apart on column names or timestamp formats.
"""

from __future__ import annotations

from typing import Final

#: Canonical timestamp format used in every CSV column and API payload.
ETA_FORMAT: Final[str] = "%Y-%m-%d %H:%M"

#: Columns a vessel schedule CSV must provide.
VESSEL_COLUMNS: Final[tuple[str, ...]] = (
    "vessel_id",
    "name",
    "eta",
    "size_teu",
    "cargo_type",
    "priority",
)

#: Columns a berth capacity CSV must provide.
BERTH_COLUMNS: Final[tuple[str, ...]] = (
    "berth_id",
    "capacity_teu",
    "crane_count",
    "avg_dwell_hours",
)

#: Planning horizon, in 24-hour windows.
PLANNING_HORIZON_DAYS: Final[int] = 3

VESSELS_FILENAME: Final[str] = "vessels.csv"
BERTHS_FILENAME: Final[str] = "berths.csv"
ALTERNATE_PORTS_FILENAME: Final[str] = "alternate_ports.json"

#: Deliberately conservative, illustrative demo estimate ($0.05/TEU-hour) — not a quoted real-world
#: rate — chosen to keep displayed cost figures realistic and demo-credible.
DEMURRAGE_RATE_PER_TEU_HOUR: Final[float] = 0.05
