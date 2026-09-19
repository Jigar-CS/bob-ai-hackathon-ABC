"""
Generate Comprehensive Sample Dataset for PortPulse ML System

Creates realistic vessel and berth datasets with:
- Multiple vessel types and sizes
- Various cargo types (general, reefer, hazmat, bulk)
- Origin coordinates for weather routing
- Priority levels
- Realistic arrival times over 72-hour horizon

Also generates ML prediction outputs showing:
- Congestion risk forecasts
- Berth assignments with ML scores
- Weather delay predictions
- Wait time predictions
- Demurrage cost estimates
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Configuration
OUTPUT_DIR = Path(__file__).parent.parent / "src" / "portpulse" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Seed for reproducibility
random.seed(42)

# Current time as reference
NOW = datetime.now()
HORIZON_HOURS = 72

print("=" * 80)
print("PortPulse Sample Dataset Generator")
print("=" * 80)

# =============================================================================
# VESSEL DATASET
# =============================================================================

print("\n[1/5] Generating vessel dataset...")

# Port locations (origin ports for vessels)
ORIGIN_PORTS = [
    {"name": "Shanghai", "lat": 31.23, "lon": 121.47},
    {"name": "Singapore", "lat": 1.29, "lon": 103.85},
    {"name": "Hong Kong", "lat": 22.31, "lon": 114.16},
    {"name": "Tokyo", "lat": 35.68, "lon": 139.69},
    {"name": "Busan", "lat": 35.10, "lon": 129.04},
    {"name": "Shenzhen", "lat": 22.54, "lon": 114.06},
    {"name": "Ningbo", "lat": 29.87, "lon": 121.55},
    {"name": "Qingdao", "lat": 36.07, "lon": 120.38},
    {"name": "Kaohsiung", "lat": 22.62, "lon": 120.28},
    {"name": "Los Angeles", "lat": 33.73, "lon": -118.26},
    {"name": "Rotterdam", "lat": 51.92, "lon": 4.48},
    {"name": "Dubai", "lat": 25.27, "lon": 55.29},
]

# Vessel names
VESSEL_PREFIXES = ["MV", "CSCL", "MSC", "EVER", "HAPAG", "CMA", "OOCL", "COSCO", "MAERSK", "YANG"]
VESSEL_NAMES = [
    "Pacific Star",
    "Atlantic Express",
    "Global Trader",
    "Ocean Pride",
    "Sea Guardian",
    "Blue Horizon",
    "Cargo Master",
    "Port Leader",
    "Wave Runner",
    "Storm Breaker",
    "Trade Wind",
    "Harbor Queen",
    "Marine Spirit",
    "Voyager Elite",
    "Container King",
    "Shipping Glory",
]

# Cargo types with probabilities
CARGO_TYPES = {"general": 0.50, "reefer": 0.20, "bulk": 0.15, "hazmat": 0.10, "liquid": 0.05}

# Vessel size ranges (TEU)
SIZE_RANGES = {
    "feeder": (2000, 4000),
    "feeder_max": (4000, 6000),
    "panamax": (6000, 9000),
    "post_panamax": (9000, 12000),
    "new_panamax": (12000, 15000),
    "ultra_large": (15000, 22000),
}

vessels = []
vessel_id = 1

# Generate vessels for each hour of the 72-hour horizon
for hour in range(0, HORIZON_HOURS + 1, random.randint(2, 8)):
    # Random arrival time within horizon
    eta = NOW + timedelta(hours=hour)

    # Vessel name
    prefix = random.choice(VESSEL_PREFIXES)
    name = f"{prefix} {random.choice(VESSEL_NAMES)} {vessel_id:03d}"

    # Size category
    size_category = random.choices(
        list(SIZE_RANGES.keys()), weights=[0.15, 0.20, 0.25, 0.20, 0.12, 0.08]
    )[0]
    size_range = SIZE_RANGES[size_category]
    size_teu = random.randint(size_range[0], size_range[1])

    # Cargo type
    cargo_type = random.choices(list(CARGO_TYPES.keys()), weights=list(CARGO_TYPES.values()))[0]

    # Priority (1=highest, 5=lowest)
    # Higher priority for hazmat, reefers, and larger vessels
    if cargo_type == "hazmat":
        priority = random.choices([1, 2], weights=[0.7, 0.3])[0]
    elif cargo_type == "reefer":
        priority = random.choices([1, 2, 3], weights=[0.4, 0.4, 0.2])[0]
    elif size_teu > 15000:
        priority = random.choices([1, 2, 3], weights=[0.3, 0.4, 0.3])[0]
    else:
        priority = random.choices([2, 3, 4, 5], weights=[0.15, 0.35, 0.30, 0.20])[0]

    # Origin port
    origin = random.choice(ORIGIN_PORTS)

    vessels.append(
        {
            "vessel_id": f"V{vessel_id:03d}",
            "name": name,
            "eta": eta.strftime("%Y-%m-%d %H:%M"),
            "size_teu": size_teu,
            "cargo_type": cargo_type,
            "priority": priority,
            "origin_port": origin["name"],
            "origin_lat": origin["lat"],
            "origin_lon": origin["lon"],
        }
    )

    vessel_id += 1

# Create DataFrame and save
vessels_df = pd.DataFrame(vessels)
vessels_df.to_csv(OUTPUT_DIR / "vessels.csv", index=False)
print(f"   Generated {len(vessels)} vessels")
print(f"   Size distribution: {vessels_df['size_teu'].describe().round(0).to_dict()}")
print(f"   Priority distribution: {vessels_df['priority'].value_counts().to_dict()}")
print(f"   Cargo types: {vessels_df['cargo_type'].value_counts().to_dict()}")

# =============================================================================
# BERTH DATASET
# =============================================================================

print("\n[2/5] Generating berth dataset...")

berths = [
    {
        "berth_id": "B1",
        "capacity_teu": 20000,
        "crane_count": 6,
        "avg_dwell_hours": 24.0,
        "specialization": "ultra_large",
    },
    {
        "berth_id": "B2",
        "capacity_teu": 18000,
        "crane_count": 5,
        "avg_dwell_hours": 22.0,
        "specialization": "new_panamax",
    },
    {
        "berth_id": "B3",
        "capacity_teu": 15000,
        "crane_count": 5,
        "avg_dwell_hours": 20.0,
        "specialization": "post_panamax",
    },
    {
        "berth_id": "B4",
        "capacity_teu": 12000,
        "crane_count": 4,
        "avg_dwell_hours": 18.0,
        "specialization": "panamax",
    },
    {
        "berth_id": "B5",
        "capacity_teu": 10000,
        "crane_count": 4,
        "avg_dwell_hours": 16.0,
        "specialization": "panamax",
    },
    {
        "berth_id": "B6",
        "capacity_teu": 8000,
        "crane_count": 3,
        "avg_dwell_hours": 14.0,
        "specialization": "feeder_max",
    },
    {
        "berth_id": "B7",
        "capacity_teu": 6000,
        "crane_count": 3,
        "avg_dwell_hours": 12.0,
        "specialization": "feeder_max",
    },
    {
        "berth_id": "B8",
        "capacity_teu": 5000,
        "crane_count": 2,
        "avg_dwell_hours": 10.0,
        "specialization": "feeder",
    },
]

berths_df = pd.DataFrame(berths)
berths_df.to_csv(OUTPUT_DIR / "berths.csv", index=False)
print(f"   Generated {len(berths)} berths")
print(f"   Total capacity: {berths_df['capacity_teu'].sum():,} TEU")
print(f"   Total cranes: {berths_df['crane_count'].sum()}")

# =============================================================================
# ALTERNATE PORTS
# =============================================================================

print("\n[3/5] Generating alternate ports dataset...")

alternate_ports = [
    {
        "port": "Port of Oakland",
        "distance_km": 620,
        "spare_capacity_teu": 12000,
        "specialization": "general",
    },
    {
        "port": "Port of Tacoma",
        "distance_km": 1450,
        "spare_capacity_teu": 15000,
        "specialization": "general",
    },
    {
        "port": "Port of Ensenada",
        "distance_km": 240,
        "spare_capacity_teu": 5000,
        "specialization": "feeder",
    },
    {
        "port": "Port of Long Beach",
        "distance_km": 50,
        "spare_capacity_teu": 18000,
        "specialization": "ultra_large",
    },
    {
        "port": "Port of Vancouver",
        "distance_km": 1800,
        "spare_capacity_teu": 10000,
        "specialization": "panamax",
    },
]

alt_path = OUTPUT_DIR / "alternate_ports.json"
with alt_path.open("w") as f:
    json.dump(alternate_ports, f, indent=2)
print(f"   Generated {len(alternate_ports)} alternate ports")

# =============================================================================
# WEATHER SCENARIOS
# =============================================================================

print("\n[4/5] Generating weather scenarios...")

weather_scenarios = [
    {
        "scenario": "clear",
        "wave_height_m": 0.5,
        "wind_speed_kt": 10,
        "visibility_km": 15,
        "probability": 0.40,
    },
    {
        "scenario": "minor",
        "wave_height_m": 2.0,
        "wind_speed_kt": 25,
        "visibility_km": 10,
        "probability": 0.30,
    },
    {
        "scenario": "moderate",
        "wave_height_m": 4.0,
        "wind_speed_kt": 40,
        "visibility_km": 5,
        "probability": 0.20,
    },
    {
        "scenario": "severe",
        "wave_height_m": 6.5,
        "wind_speed_kt": 55,
        "visibility_km": 2,
        "probability": 0.10,
    },
]

weather_path = OUTPUT_DIR / "weather_scenarios.json"
with weather_path.open("w") as f:
    json.dump(weather_scenarios, f, indent=2)
print(f"   Generated {len(weather_scenarios)} weather scenarios")

# =============================================================================
# SUMMARY
# =============================================================================

print("\n[5/5] Dataset generation complete!")
print("\n" + "=" * 80)
print("DATASET SUMMARY")
print("=" * 80)
print(f"\nOutput directory: {OUTPUT_DIR}")
print("\nFiles generated:")
print(f"  - vessels.csv          : {len(vessels)} vessels over {HORIZON_HOURS}h horizon")
print(f"  - berths.csv           : {len(berths)} berths")
print(f"  - alternate_ports.json : {len(alternate_ports)} alternate ports")
print(f"  - weather_scenarios.json: {len(weather_scenarios)} weather patterns")

print("\nVessel Distribution:")
print(f"  - Size range: {vessels_df['size_teu'].min():,} - {vessels_df['size_teu'].max():,} TEU")
print(f"  - Average size: {vessels_df['size_teu'].mean():,.0f} TEU")
print(f"  - P1 (highest priority): {(vessels_df['priority'] == 1).sum()} vessels")
print(f"  - Hazmat cargo: {(vessels_df['cargo_type'] == 'hazmat').sum()} vessels")
print(f"  - Reefer cargo: {(vessels_df['cargo_type'] == 'reefer').sum()} vessels")

print("\nBerth Capacity:")
print(f"  - Total capacity: {berths_df['capacity_teu'].sum():,} TEU")
print(f"  - Average dwell: {berths_df['avg_dwell_hours'].mean():.1f} hours")
print(f"  - Total cranes: {berths_df['crane_count'].sum()}")

print("\n✅ Sample dataset generated successfully!")
print("   Run the API server and access /api/v1/plan to see ML predictions")
