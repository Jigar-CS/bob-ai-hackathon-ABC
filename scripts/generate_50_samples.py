"""Script to generate 50-record vessel and berth CSV test datasets for PortPulse."""

import random
from datetime import datetime, timedelta
from pathlib import Path


def generate_datasets() -> None:
    random.seed(42)
    start_time = datetime(2026, 9, 20, 0, 0)

    # 1. Vessels (50 records)
    vessel_names = [
        "Horizon",
        "Pacific",
        "Ocean",
        "Global",
        "Atlantic",
        "Titan",
        "Voyager",
        "Express",
        "Neptune",
        "Star",
        "Pioneer",
        "Mermaid",
        "Poseidon",
        "Mariner",
        "Endeavour",
        "Navigator",
        "Trader",
        "Carrier",
        "Frontier",
        "Discovery",
        "Valor",
        "Apex",
    ]
    cargo_types = ["general", "reefer", "hazmat", "bulk"]

    vessels_lines = ["vessel_id,name,eta,size_teu,cargo_type,priority"]
    for i in range(1, 51):
        vid = f"V{i:03d}"
        prefix = random.choice(["MV", "SS", "MS"])
        name = f"{prefix} {random.choice(vessel_names)}-{i}"
        # Spread ETAs across 72 hours
        hours_offset = random.randint(0, 70)
        minutes_offset = random.choice([0, 15, 30, 45])
        eta_dt = start_time + timedelta(hours=hours_offset, minutes=minutes_offset)
        eta_str = eta_dt.strftime("%Y-%m-%d %H:%M")
        size_teu = random.choice([3000, 4500, 6000, 8000, 10000, 12000, 15000, 18000, 20000])
        cargo = random.choice(cargo_types)
        priority = random.choice([1, 1, 2, 2, 2, 3, 3])  # Weight prio 1 and 2
        vessels_lines.append(f"{vid},{name},{eta_str},{size_teu},{cargo},{priority}")

    vessels_csv = "\n".join(vessels_lines) + "\n"
    out_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "test_vessels_50.csv").write_text(vessels_csv, encoding="utf-8")

    # 2. Berths (50 records)
    berths_lines = ["berth_id,capacity_teu,crane_count,avg_dwell_hours"]
    for i in range(1, 51):
        bid = f"B{i:02d}"
        capacity = random.choice([8000, 10000, 12000, 16000, 20000, 24000])
        cranes = random.choice([2, 3, 4, 5, 6])
        dwell = round(random.uniform(12.0, 36.0), 1)
        berths_lines.append(f"{bid},{capacity},{cranes},{dwell}")

    berths_csv = "\n".join(berths_lines) + "\n"
    (out_dir / "test_berths_50.csv").write_text(berths_csv, encoding="utf-8")

    print(f"Successfully generated 50-record datasets in {out_dir}.")


if __name__ == "__main__":
    generate_datasets()
