"""Berth Swap Optimizer module.

Analyzes pairs of assigned vessels to identify valid berth swaps that reduce
queue wait time or improve priority alignment without altering core planning logic.
"""

from __future__ import annotations

import logging
from typing import Any

from portpulse.constants import DEMURRAGE_RATE_PER_TEU_HOUR

logger = logging.getLogger(__name__)


def find_swap_opportunities(
    assignments: list[dict[str, Any]],
    berths: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Identify advisory berth swap opportunities across assigned vessels.

    For every pair of assigned vessels, check if swapping their berths is
    physically valid (each vessel fits the target berth capacity) and produces a
    net reduction in wait time or better priority placement.

    Args:
        assignments: List of assigned vessel dictionaries from OpsPlan.
        berths: Optional list of berth capacity dictionaries.

    Returns:
        List of swap opportunity dictionaries matching :class:`SwapOpportunity`.
    """
    if len(assignments) < 2:
        return []

    # Map berth capacities if provided
    berth_caps: dict[str, int] = {}
    if berths:
        for b in berths:
            bid = str(b.get("berth_id", "")).strip().upper()
            try:
                berth_caps[bid] = int(b.get("capacity_teu", 16000))
            except (ValueError, TypeError):
                berth_caps[bid] = 16000

    opportunities: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i in range(len(assignments)):
        for j in range(i + 1, len(assignments)):
            v1 = assignments[i]
            v2 = assignments[j]

            id1 = str(v1.get("vessel_id", f"V{i}"))
            id2 = str(v2.get("vessel_id", f"V{j}"))

            pair_key: tuple[str, str] = (min(id1, id2), max(id1, id2))
            if pair_key in seen_pairs:
                continue

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

            p1 = int(v1.get("priority", 2))
            p2 = int(v2.get("priority", 2))
            w1 = float(v1.get("wait_hours", 0.0))
            w2 = float(v2.get("wait_hours", 0.0))

            hours_saved = 0.0
            reason = ""

            # Condition 1: P1 vessel waiting longer than P2/P3 vessel at a different berth
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
            # Condition 2: Overall wait time reduction
            elif (w1 + w2) > 3.0 and abs(w1 - w2) >= 1.5:
                hours_saved = round(abs(w1 - w2) / 2.0, 2)
                higher_wait_vessel = v1.get("vessel_name") if w1 > w2 else v2.get("vessel_name")
                reason = (
                    f"Re-allocating {higher_wait_vessel} balances berth crane loading "
                    f"and saves approximately {hours_saved}h combined queue wait."
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
                seen_pairs.add(pair_key)

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
