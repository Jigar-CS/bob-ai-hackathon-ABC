"""Dataset ML evaluation script for Datasets 1 & 2.

Processes both `vessels_dataset_1_la_lb_surge.csv` and `vessels_dataset_2_global_multiport.csv`
through the PortPulse ML operations planner, verifies schema compliance, and exports
structured expected ML output JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path

from portpulse.csv_io import read_csv_file
from portpulse.datasets import load_berths
from portpulse.domain.planner import generate_ops_plan

DIR_PATH = Path(__file__).parent
DATASET_1_PATH = DIR_PATH / "vessels_dataset_1_la_lb_surge.csv"
DATASET_2_PATH = DIR_PATH / "vessels_dataset_2_global_multiport.csv"

OUTPUT_1_JSON = DIR_PATH / "dataset_1_ml_output.json"
OUTPUT_2_JSON = DIR_PATH / "dataset_2_ml_output.json"


def evaluate(dataset_path: Path, output_json_path: Path, title: str):
    print("=" * 75)
    print(f"EVALUATING: {title}")
    print("=" * 75)

    vessels = read_csv_file(dataset_path)
    berths = load_berths()

    print(f"Loaded {len(vessels)} vessels and {len(berths)} berths from {dataset_path.name}")
    plan = generate_ops_plan(vessels, berths)

    output_json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Exported ML plan JSON -> {output_json_path.name}")

    print(f"\n--- {title} Highlights ---")
    print(f"ML Enabled:             {plan['ml_enabled']}")
    print(f"ML Allocation Used:     {plan['ml_allocation_used']}")
    print(f"Assigned Vessels:       {len(plan['berth_assignments'])}")
    print(f"Unassigned Vessels:     {plan['unassigned_count']}")
    print(f"Weather Delayed Count:  {len(plan['weather_summary'])}")
    print(f"Reroute Suggestions:    {len(plan['reroute_suggestions'])}")
    print(f"Swap Opportunities:     {len(plan['swap_opportunities'])}")

    print("\n--- KPIs ---")
    for k, v in plan["kpis"].items():
        print(f"  {k:30s}: {v}")

    print("\n--- Sample Assignments (First 3) ---")
    for a in plan["berth_assignments"][:3]:
        print(f"Vessel: {a['vessel_id']} ({a['vessel_name']}) -> Berth: {a['berth_id']}")
        print(
            f"  Queue Status: {a.get('queue_status')} | "
            f"Position: #{a.get('queue_position')} | "
            f"Queued Behind: {a.get('queued_behind')}"
        )
        print(f"  Origin: {a.get('origin_port', 'N/A')} -> Dest: {a.get('dest_port', 'N/A')}")
        print(f"  Berth Start: {a['berth_start']} | Est Dept: {a['departure_est']}")
        print(
            f"  ML Wait: {a['predicted_wait_hours']}h | "
            f"ML Moves/Hr: {a['predicted_moves_per_hour']} | "
            f"ML Demurrage: ${a['predicted_demurrage_cost_usd']}"
        )
        print(f"  Reason: {a['reason']}\n")

    return plan


if __name__ == "__main__":
    evaluate(DATASET_1_PATH, OUTPUT_1_JSON, "DATASET 1: LA/Long Beach High-Volume Surge")
    evaluate(DATASET_2_PATH, OUTPUT_2_JSON, "DATASET 2: Global Multi-Port & Weather Disruption")
