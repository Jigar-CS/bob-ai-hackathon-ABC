"""Cascading Impact Simulator module.

Simulates multi-pass schedule disruption ripples across vessel queues and berths,
tracking cascade depth, total delay hours, and demurrage cost impact.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from portpulse.config import get_settings
from portpulse.constants import DEMURRAGE_RATE_PER_TEU_HOUR, ETA_FORMAT
from portpulse.csv_io import Row
from portpulse.domain.planner import generate_ops_plan

logger = logging.getLogger(__name__)

HARD_MAX_ITERATIONS = 10
HARD_MAX_VESSELS = 500


def simulate_cascade(
    vessels: list[Row],
    berths: list[Row],
    disruption: dict[str, Any],
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Simulate iterative cascading disruptions across the berth schedule.

    Args:
        vessels: List of vessel schedule rows.
        berths: List of berth capacity rows.
        disruption: Disruption spec dict with ``type`` ('delay_vessel' | 'berth_outage').
        max_iterations: Maximum simulation passes (capped at 10).

    Returns:
        Dict with keys: ``iterations_run``, ``stabilized``, ``total_vessels_affected``,
        ``total_cascade_delay_hours``, ``total_estimated_cost``, and ``affected_vessels``.
    """
    # Safety guards for live demos
    warnings: list[str] = []
    if len(vessels) > HARD_MAX_VESSELS:
        warnings.append(f"Input truncated from {len(vessels)} to {HARD_MAX_VESSELS} vessels.")
        vessels = vessels[:HARD_MAX_VESSELS]
    iterations_cap = min(max(1, max_iterations), HARD_MAX_ITERATIONS)

    # 1. Baseline plan
    baseline_plan = generate_ops_plan(vessels, berths)
    base_assignments = {
        str(a.get("vessel_id")): a for a in (baseline_plan.get("berth_assignments") or [])
    }
    base_vessel_map = {str(v.get("vessel_id")): v for v in vessels}

    curr_vessels = [dict(v) for v in vessels]
    curr_berths = [dict(b) for b in berths]

    scen_type = str(disruption.get("type", "")).strip().lower()

    # 2. Initial Disruption application
    if scen_type == "delay_vessel":
        target_vid = str(disruption.get("vessel_id", "")).strip().lower()
        delay_hrs = float(disruption.get("delay_hours", 0.0))
        if delay_hrs <= 0:
            warnings.append("delay_hours must be greater than 0; disruption ignored.")
        for v in curr_vessels:
            vid = str(v.get("vessel_id", "")).strip().lower()
            if vid == target_vid:
                raw_eta = str(v.get("eta", ""))
                try:
                    dt_eta = datetime.strptime(raw_eta, ETA_FORMAT)
                    v["eta"] = (dt_eta + timedelta(hours=delay_hrs)).strftime(ETA_FORMAT)
                except ValueError:
                    logger.warning("Invalid eta '%s' in cascade disruption", raw_eta)

    elif scen_type == "berth_outage":
        target_bid = str(disruption.get("berth_id", "")).strip().lower()
        curr_berths = [
            b for b in curr_berths if str(b.get("berth_id", "")).strip().lower() != target_bid
        ]

    affected_map: dict[str, dict[str, Any]] = {}
    prev_starts: dict[str, str] = {
        vid: str(a.get("berth_start", "")) for vid, a in base_assignments.items()
    }

    iterations_run = 0
    stabilized = False

    # 3. Iterative Cascade Passes
    for iter_num in range(1, iterations_cap + 1):
        iterations_run = iter_num
        iter_plan = generate_ops_plan(curr_vessels, curr_berths)
        iter_assignments = {
            str(a.get("vessel_id")): a for a in (iter_plan.get("berth_assignments") or [])
        }

        new_cascade_hits = 0

        for vid, base_a in base_assignments.items():
            base_start_str = str(base_a.get("berth_start", ""))
            vname = str(base_a.get("vessel_name", vid))

            try:
                base_start_dt = datetime.strptime(base_start_str, ETA_FORMAT)
            except ValueError:
                continue

            if vid not in iter_assignments:
                # Pushed to unassigned
                if vid not in affected_map:
                    max_wait = float(get_settings().app.max_berth_wait_hours)
                    affected_map[vid] = {
                        "vessel_id": vid,
                        "vessel_name": vname,
                        "delay_hours": max_wait,  # Max wait penalty
                        "cascade_depth": iter_num,
                        "reason": f"Pushed to unassigned queue during pass #{iter_num}",
                        "size_teu": int(base_vessel_map.get(vid, {}).get("size_teu", 6500)),
                    }
                    new_cascade_hits += 1
            else:
                curr_a = iter_assignments[vid]
                curr_start_str = str(curr_a.get("berth_start", ""))
                try:
                    curr_start_dt = datetime.strptime(curr_start_str, ETA_FORMAT)
                    delay_hours = (curr_start_dt - base_start_dt).total_seconds() / 3600.0
                except ValueError:
                    delay_hours = 0.0

                if delay_hours > 0.05 and vid not in affected_map:
                    affected_map[vid] = {
                        "vessel_id": vid,
                        "vessel_name": vname,
                        "delay_hours": round(delay_hours, 2),
                        "cascade_depth": iter_num,
                        "reason": (
                            f"Berth start delayed by {round(delay_hours, 1)}h "
                            f"(Pass #{iter_num}: {base_start_str} -> {curr_start_str})"
                        ),
                        "size_teu": int(base_vessel_map.get(vid, {}).get("size_teu", 6500)),
                    }
                    new_cascade_hits += 1

        # Check stabilization
        current_starts = {vid: str(a.get("berth_start", "")) for vid, a in iter_assignments.items()}
        if current_starts == prev_starts or new_cascade_hits == 0:
            stabilized = True
            break

        prev_starts = current_starts

        # Propagate delays into vessel ETAs for subsequent pass (only for affected vessels)
        for v in curr_vessels:
            vid = str(v.get("vessel_id"))
            if vid in iter_assignments and vid in affected_map:
                v["eta"] = iter_assignments[vid].get("berth_start", v.get("eta"))

    affected_list: list[dict[str, Any]] = list(affected_map.values())
    affected_list.sort(key=lambda x: (int(x["cascade_depth"]), -float(x["delay_hours"])))

    total_vessels_affected = len(affected_list)
    total_cascade_delay_hours = round(sum(v["delay_hours"] for v in affected_list), 2)

    # Demurrage cost calculation
    total_cost = 0.0
    for item in affected_list:
        delay = float(item.get("delay_hours", 0.0))
        size = int(item.get("size_teu", 6500))
        cost = delay * size * DEMURRAGE_RATE_PER_TEU_HOUR
        item["cost_impact"] = round(cost, 2)
        total_cost += cost

    return {
        "iterations_run": iterations_run,
        "stabilized": stabilized,
        "total_vessels_affected": total_vessels_affected,
        "total_cascade_delay_hours": total_cascade_delay_hours,
        "total_estimated_cost": round(total_cost, 2),
        "affected_vessels": affected_list,
        "warnings": warnings,
    }
