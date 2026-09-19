"""Dataset ML evaluation script.

Loads `vessels_test_20.csv`, processes it through the PortPulse ML operations planner,
and prints/saves the comprehensive ML analysis output.
"""

from __future__ import annotations

import json
from pathlib import Path

from portpulse.csv_io import read_csv_file
from portpulse.datasets import load_berths
from portpulse.domain.planner import generate_ops_plan

DATASET_PATH = Path(__file__).parent / "vessels_test_20.csv"
OUTPUT_JSON_PATH = Path(__file__).parent / "expected_ml_output.json"


def run_evaluation():
    print(f"Loading test dataset from {DATASET_PATH}...")
    vessels = read_csv_file(DATASET_PATH)
    berths = load_berths()

    print(f"Loaded {len(vessels)} vessels and {len(berths)} berths.")
    print("Executing ML Operations Planner...")

    plan = generate_ops_plan(vessels, berths)

    # Save expected output JSON
    OUTPUT_JSON_PATH.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"Saved complete ML output to {OUTPUT_JSON_PATH}")

    # Display key highlights
    print("\n" + "=" * 70)
    print("                PORTPULSE ML EVALUATION HIGHLIGHTS")
    print("=" * 70)

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

    print("\n--- Sample Berth Assignments (First 5) ---")
    for a in plan["berth_assignments"][:5]:
        print(f"Vessel: {a['vessel_id']} ({a['vessel_name']}) -> Berth: {a['berth_id']}")
        print(f"  Priority: P{a['priority']} | Size: {a['size_teu']} TEU | Cargo: {a['cargo_type']}")
        print(f"  Berth Start: {a['berth_start']} | Est. Dept: {a['departure_est']}")
        print(f"  ML Pred Wait Hours:    {a['predicted_wait_hours']} h")
        print(f"  ML Pred Demurrage USD: ${a['predicted_demurrage_cost_usd']}")
        print(f"  ML Pred Moves/Hr:      {a['predicted_moves_per_hour']}")
        print(f"  ML Anomaly Flagged:    {a['is_anomalous']}")
        print(f"  Reason: {a['reason']}\n")

    if plan["reroute_suggestions"]:
        print("--- Alternate Reroute Suggestions (Unassigned Vessels) ---")
        for r in plan["reroute_suggestions"]:
            print(f"Unassigned Vessel {r['vessel_id']} ({r['vessel_name']}):")
            print(f"  Recommended Port: {r.get('recommended_port', 'N/A')}")
            print(f"  Reasoning: {r.get('recommendation_reason', 'N/A')}\n")

    return plan


if __name__ == "__main__":
    run_evaluation()
