"""What-If Scenario Simulator module.

Executes sandboxed scenario simulations by calling generate_ops_plan() twice
(baseline vs modified scenario) and computing a diff summary.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from portpulse.constants import ETA_FORMAT
from portpulse.csv_io import Row
from portpulse.domain.planner import generate_ops_plan

logger = logging.getLogger(__name__)


def simulate_whatif(
    vessels: list[Row],
    berths: list[Row],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Run a sandboxed What-If simulation comparing baseline vs modified scenario.

    Args:
        vessels: List of vessel schedule rows.
        berths: List of berth capacity rows.
        scenario: Dict with ``type`` ('delay_vessel' | 'berth_outage') and parameters.

    Returns:
        Dict with keys: ``scenario``, ``baseline_plan``, ``modified_plan``, ``diff_summary``.
    """
    baseline_plan = generate_ops_plan(vessels, berths)

    scen_type = str(scenario.get("type", "")).strip().lower()
    mod_vessels = [dict(v) for v in vessels]
    mod_berths = [dict(b) for b in berths]

    if scen_type == "delay_vessel":
        target_vid = str(scenario.get("vessel_id", "")).strip().lower()
        delay_hrs = float(scenario.get("delay_hours", 0.0))

        for v in mod_vessels:
            vid = str(v.get("vessel_id", "")).strip().lower()
            if vid == target_vid:
                raw_eta = str(v.get("eta", ""))
                try:
                    dt_eta = datetime.strptime(raw_eta, ETA_FORMAT)
                    new_eta = dt_eta + timedelta(hours=delay_hrs)
                    v["eta"] = new_eta.strftime(ETA_FORMAT)
                except ValueError:
                    logger.warning("Could not parse eta '%s' for delay scenario", raw_eta)

    elif scen_type == "berth_outage":
        target_bid = str(scenario.get("berth_id", "")).strip().lower()
        # Remove or disable target berth from schedule
        mod_berths = [
            b for b in mod_berths if str(b.get("berth_id", "")).strip().lower() != target_bid
        ]

    modified_plan = generate_ops_plan(mod_vessels, mod_berths)

    # Compute diff summary
    base_assignments = {
        str(a.get("vessel_id")): a for a in baseline_plan.get("berth_assignments") or []
    }
    mod_assignments = {
        str(a.get("vessel_id")): a for a in modified_plan.get("berth_assignments") or []
    }

    reassigned_vessels: list[dict[str, str]] = []
    newly_unassigned_vessels: list[dict[str, str]] = []

    for vid, base_a in base_assignments.items():
        vname = str(base_a.get("vessel_name", vid))
        if vid not in mod_assignments:
            newly_unassigned_vessels.append(
                {
                    "vessel_id": vid,
                    "vessel_name": vname,
                    "baseline_berth": str(base_a.get("berth_id", "—")),
                    "reason": "Pushed to unassigned/reroute queue in scenario",
                }
            )
        else:
            mod_a = mod_assignments[vid]
            base_b = str(base_a.get("berth_id", ""))
            mod_b = str(mod_a.get("berth_id", ""))
            base_start = str(base_a.get("berth_start", ""))
            mod_start = str(mod_a.get("berth_start", ""))

            if base_b != mod_b or base_start != mod_start:
                reassigned_vessels.append(
                    {
                        "vessel_id": vid,
                        "vessel_name": vname,
                        "baseline_berth": base_b,
                        "modified_berth": mod_b,
                        "baseline_start": base_start,
                        "modified_start": mod_start,
                    }
                )

    # Compare risk levels by day
    base_fc = {w.get("day"): w for w in baseline_plan.get("congestion_forecast") or []}
    mod_fc = {w.get("day"): w for w in modified_plan.get("congestion_forecast") or []}
    risk_level_changes: list[dict[str, Any]] = []

    for day in sorted(set(base_fc.keys()) | set(mod_fc.keys())):
        b_risk = base_fc.get(day, {}).get("risk_level", "LOW")
        m_risk = mod_fc.get(day, {}).get("risk_level", "LOW")
        if b_risk != m_risk:
            risk_level_changes.append(
                {
                    "day": day,
                    "baseline_risk": b_risk,
                    "modified_risk": m_risk,
                }
            )

    diff_summary = {
        "reassigned_count": len(reassigned_vessels),
        "newly_unassigned_count": len(newly_unassigned_vessels),
        "reassigned_vessels": reassigned_vessels,
        "newly_unassigned_vessels": newly_unassigned_vessels,
        "risk_level_changes": risk_level_changes,
    }

    return {
        "scenario": scenario,
        "baseline_plan": baseline_plan,
        "modified_plan": modified_plan,
        "diff_summary": diff_summary,
    }
