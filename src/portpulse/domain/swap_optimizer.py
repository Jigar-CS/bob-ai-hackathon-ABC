"""Berth Swap Optimizer module.

Analyzes pairs of assigned vessels to identify valid berth swaps that reduce
queue wait time or improve priority alignment without altering core planning logic.
"""

from __future__ import annotations

import logging
from typing import Any

from portpulse.constants import DEMURRAGE_RATE_PER_TEU_HOUR
from portpulse.domain.assignment import _is_cargo_compatible

logger = logging.getLogger(__name__)


def find_swap_opportunities(
    assignments: list[dict[str, Any]],
    berths: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Identify advisory berth swap opportunities across assigned vessels.

    For every pair of assigned vessels, check if swapping their berths is
    physically valid (each vessel fits the target berth capacity and cargo type) and produces a
    net reduction in wait time or better priority placement.

    Args:
        assignments: List of assigned vessel dictionaries from OpsPlan.
        berths: Optional list of berth capacity dictionaries.

    Returns:
        List of swap opportunity dictionaries matching :class:`SwapOpportunity`.
    """
    if len(assignments) < 2:
        return []
    if len(assignments) > 200:
        assignments = assignments[:200]

    # Map berth capacities, crane counts, and allowed cargo types if provided
    berth_caps: dict[str, int] = {}
    berth_cranes: dict[str, int] = {}
    berth_cargos: dict[str, str] = {}
    if berths:
        for b in berths:
            bid = str(b.get("berth_id", "")).strip().upper()
            try:
                berth_caps[bid] = int(b.get("capacity_teu", 16000))
            except (ValueError, TypeError):
                berth_caps[bid] = 16000
            try:
                berth_cranes[bid] = int(b.get("crane_count", 2))
            except (ValueError, TypeError):
                berth_cranes[bid] = 2
            berth_cargos[bid] = str(b.get("allowed_cargo_types") or "all").strip()

    opportunities: list[dict[str, Any]] = []

    for i in range(len(assignments)):
        for j in range(i + 1, len(assignments)):
            v1 = assignments[i]
            v2 = assignments[j]

            id1 = str(v1.get("vessel_id", f"V{i}"))
            id2 = str(v2.get("vessel_id", f"V{j}"))

            b1_id = str(v1.get("berth_id", "B1")).strip().upper()
            b2_id = str(v2.get("berth_id", "B2")).strip().upper()

            # Skip if assigned to the same berth
            if b1_id == b2_id:
                continue

            # Physical capacity check
            size1 = int(v1.get("size_teu", 6500))
            size2 = int(v2.get("size_teu", 6500))

            cap1 = berth_caps.get(b1_id, 18000)
            cap2 = berth_caps.get(b2_id, 18000)

            # Vessel 1 must fit Berth 2, Vessel 2 must fit Berth 1
            if size1 > cap2 or size2 > cap1:
                continue

            # Cargo type compatibility check for swap targets
            cargo1 = str(v1.get("cargo_type") or "general")
            cargo2 = str(v2.get("cargo_type") or "general")
            allowed1 = berth_cargos.get(b1_id, "all")
            allowed2 = berth_cargos.get(b2_id, "all")
            if not _is_cargo_compatible(cargo1, allowed2) or not _is_cargo_compatible(
                cargo2, allowed1
            ):
                continue

            # Temporal schedule check: vessel cannot start berthing after target departure
            arr1 = str(v1.get("arrival", "")).strip()
            arr2 = str(v2.get("arrival", "")).strip()
            b1_dep = str(v1.get("departure_est", "")).strip()
            b2_dep = str(v2.get("departure_est", "")).strip()

            if arr1 and b2_dep and arr1 > b2_dep:
                continue
            if arr2 and b1_dep and arr2 > b1_dep:
                continue

            p1 = int(v1.get("priority", 2))
            p2 = int(v2.get("priority", 2))
            # Prefer ML-predicted wait hours when available for more accurate savings estimates
            raw_w1 = float(v1.get("wait_hours", 0.0))
            raw_w2 = float(v2.get("wait_hours", 0.0))
            ml_w1 = v1.get("predicted_wait_hours")
            ml_w2 = v2.get("predicted_wait_hours")
            w1 = float(ml_w1) if ml_w1 is not None else raw_w1
            w2 = float(ml_w2) if ml_w2 is not None else raw_w2

            c1 = int(v1.get("crane_count") or berth_cranes.get(b1_id, 2))
            c2 = int(v2.get("crane_count") or berth_cranes.get(b2_id, 2))

            hours_saved = 0.0
            reason = ""

            # Condition 1: P1/higher priority vessel waiting longer than P2/P3 vessel
            if p1 < p2 and w1 > w2:
                hours_saved = round(w1 - w2, 2)
                reason = (
                    f"Swapping {v1.get('vessel_name')} (P{p1}) with "
                    f"{v2.get('vessel_name')} (P{p2}) prioritizes time-critical "
                    f"cargo and reduces P1 queue wait by {hours_saved}h."
                )
            elif p2 < p1 and w2 > w1:
                hours_saved = round(w2 - w1, 2)
                reason = (
                    f"Swapping {v2.get('vessel_name')} (P{p2}) with "
                    f"{v1.get('vessel_name')} (P{p1}) prioritizes time-critical "
                    f"cargo and reduces P1 queue wait by {hours_saved}h."
                )
            # Condition 2: Priority-Crane Resource Optimization
            elif p1 < p2 and c2 > c1:
                dwell1 = float(v1.get("effective_dwell_hours", 36.0))
                saved_dwell = round(dwell1 * (1.0 - c1 / c2), 1)
                hours_saved = max(saved_dwell, 1.0)
                reason = (
                    f"Re-allocating {v1.get('vessel_name')} (P{p1}) from Berth {b1_id} "
                    f"({c1} cranes) to Berth {b2_id} ({c2} cranes) accelerates "
                    f"time-critical cargo turnaround by {hours_saved}h."
                )
            elif p2 < p1 and c1 > c2:
                dwell2 = float(v2.get("effective_dwell_hours", 36.0))
                saved_dwell = round(dwell2 * (1.0 - c2 / c1), 1)
                hours_saved = max(saved_dwell, 1.0)
                reason = (
                    f"Re-allocating {v2.get('vessel_name')} (P{p2}) from Berth {b2_id} "
                    f"({c2} cranes) to Berth {b1_id} ({c1} cranes) accelerates "
                    f"time-critical cargo turnaround by {hours_saved}h."
                )
            # Condition 3: Queue wait / load balancing
            elif (w1 + w2) > 2.0 or (w1 > 0 and w2 == 0) or (w2 > 0 and w1 == 0):
                hours_saved = round(max(abs(w1 - w2), w1, w2), 2)
                higher_wait_vessel = v1.get("vessel_name") if w1 >= w2 else v2.get("vessel_name")
                reason = (
                    f"Re-allocating {higher_wait_vessel} balances berth crane loading "
                    f"and saves approximately {hours_saved}h queue wait."
                )

            if hours_saved > 0.0:
                avg_teu = (size1 + size2) / 2.0
                # Cost savings formula: hours_saved * avg_teu * DEMURRAGE_RATE_PER_TEU_HOUR
                cost_saved = round(hours_saved * avg_teu * DEMURRAGE_RATE_PER_TEU_HOUR, 2)

                opportunities.append(
                    {
                        "vessel_1_id": id1,
                        "vessel_1_name": str(v1.get("vessel_name", id1)),
                        "vessel_2_id": id2,
                        "vessel_2_name": str(v2.get("vessel_name", id2)),
                        "hours_saved": hours_saved,
                        "estimated_cost_saved": cost_saved,
                        "reason": reason,
                    }
                )

    # Sort all opportunities by highest cost saved
    opportunities.sort(key=lambda x: x["estimated_cost_saved"], reverse=True)

    # Filter top 5 distinct techniques to prevent a single vessel from dominating all cards
    vessel_counts: dict[str, int] = {}
    top_opportunities: list[dict[str, Any]] = []

    for opp in opportunities:
        v1_id = opp["vessel_1_id"]
        v2_id = opp["vessel_2_id"]

        if vessel_counts.get(v1_id, 0) < 2 and vessel_counts.get(v2_id, 0) < 2:
            top_opportunities.append(opp)
            vessel_counts[v1_id] = vessel_counts.get(v1_id, 0) + 1
            vessel_counts[v2_id] = vessel_counts.get(v2_id, 0) + 1

        if len(top_opportunities) == 5:
            break

    return top_opportunities
