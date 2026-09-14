#!/usr/bin/env python3
"""Generate synthetic vessel and berth datasets.

The repository ships a committed sample dataset, so this script is only needed to
refresh it or to produce a larger set for load testing.

Examples::

    python scripts/generate_sample_data.py
    python scripts/generate_sample_data.py --vessels 200 --berths 12 --out ./tmp-data
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from portpulse.constants import (  # noqa: E402 - path shim must run first
    BERTH_COLUMNS,
    BERTHS_FILENAME,
    ETA_FORMAT,
    PLANNING_HORIZON_DAYS,
    VESSEL_COLUMNS,
    VESSELS_FILENAME,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "src" / "portpulse" / "data"

CARGO_TYPES = ("general", "reefer", "hazmat")
BERTH_CAPACITIES = (8_000, 12_000, 16_000)
CRANE_COUNTS = (2, 3, 4)
VESSEL_SIZES = (4_000, 6_000, 9_000, 11_000)
HIGH_PRIORITY_SHARE = 0.15


def build_berths(count: int, rng: random.Random) -> list[dict[str, object]]:
    """Create ``count`` berths with plausible capacity, cranes and dwell time."""
    return [
        {
            "berth_id": f"B{index}",
            "capacity_teu": rng.choice(BERTH_CAPACITIES),
            "crane_count": rng.choice(CRANE_COUNTS),
            "avg_dwell_hours": round(rng.uniform(18, 40), 1),
        }
        for index in range(1, count + 1)
    ]


def build_vessels(
    count: int, start: datetime, horizon_hours: int, rng: random.Random
) -> list[dict[str, object]]:
    """Create ``count`` vessels arriving within ``horizon_hours`` of ``start``."""
    vessels = [
        {
            "vessel_id": f"V{index:03d}",
            "name": f"MV Horizon-{index}",
            "eta": (start + timedelta(hours=rng.uniform(0, horizon_hours))).strftime(ETA_FORMAT),
            "size_teu": rng.choice(VESSEL_SIZES),
            "cargo_type": rng.choice(CARGO_TYPES),
            # Priority 1 is reserved for time-critical cargo such as reefers.
            "priority": 1 if rng.random() < HIGH_PRIORITY_SHARE else rng.choice([2, 3]),
        }
        for index in range(1, count + 1)
    ]
    vessels.sort(key=lambda vessel: str(vessel["eta"]))
    return vessels


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    """Write ``rows`` to ``path``, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--vessels", type=int, default=40, help="number of vessels (default: 40)")
    parser.add_argument("--berths", type=int, default=6, help="number of berths (default: 6)")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--start",
        default="2026-09-15 06:00",
        help=f"first arrival window start, as {ETA_FORMAT} (default: 2026-09-15 06:00)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed for reproducible output (default: 42)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.vessels < 1 or args.berths < 1:
        print("--vessels and --berths must both be at least 1", file=sys.stderr)
        return 2
    try:
        start = datetime.strptime(args.start, ETA_FORMAT)
    except ValueError:
        print(f"--start must match '{ETA_FORMAT}', e.g. 2026-09-15 06:00", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    horizon_hours = 24 * PLANNING_HORIZON_DAYS

    berths = build_berths(args.berths, rng)
    vessels = build_vessels(args.vessels, start, horizon_hours, rng)

    write_csv(args.out / BERTHS_FILENAME, BERTH_COLUMNS, berths)
    write_csv(args.out / VESSELS_FILENAME, VESSEL_COLUMNS, vessels)

    print(
        f"Wrote {len(berths)} berths and {len(vessels)} vessels "
        f"({horizon_hours}h horizon from {args.start}) to {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
