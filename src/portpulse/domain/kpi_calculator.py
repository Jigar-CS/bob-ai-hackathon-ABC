"""KPI summary calculation module.

Computes high-level operations metrics (wait time, utilization, unassigned count,
and emissions savings) from existing plan data without modifying core algorithms.
"""

from __future__ import annotations

import logging
from typing import Any

from portpulse.config import get_settings
from portpulse.constants import DEMURRAGE_RATE_PER_TEU_HOUR

logger = logging.getLogger(__name__)


def calculate_plan_kpis(plan: dict[str, Any]) -> dict[str, float | int]:
    """Calculate summary KPIs from plan data.

    Args:
        plan: The operations plan dictionary containing ``berth_assignments``,
            ``unassigned_count``, and ``congestion_forecast``.

    Returns:
        Dict with keys: ``avg_wait_hours``, ``berth_utilization_pct``,
        ``vessels_at_risk``, and ``estimated_emissions_saved_kg``.
    """
    assignments = plan.get("berth_assignments") or []
    forecast = plan.get("congestion_forecast") or []
    unassigned_count = plan.get("unassigned_count", len(plan.get("reroute_suggestions") or []))

    # 1. Average wait hours
    if assignments:
        total_wait = sum(float(a.get("wait_hours", 0.0)) for a in assignments)
        avg_wait_hours = round(total_wait / len(assignments), 2)
    else:
        avg_wait_hours = 0.0

    # 2. Berth utilization percentage
    # Total assigned TEU volume vs port single-window berth throughput capacity
    total_assigned_teu = 0
    for a in assignments:
        size = a.get("size_teu")
        if size is not None:
            total_assigned_teu += int(size)
        else:
            total_assigned_teu += 6500

    single_window_capacity = max((int(w.get("total_capacity_teu", 0)) for w in forecast), default=0)
    if single_window_capacity > 0:
        berth_utilization_pct = round((total_assigned_teu / single_window_capacity) * 100, 1)
    else:
        # Default single-window berth capacity baseline (6 berths * ~15k TEU = 90k)
        berth_utilization_pct = (
            round((total_assigned_teu / 90000) * 100, 1) if total_assigned_teu else 0.0
        )

    # 3. Vessels at risk (unassigned)
    vessels_at_risk = int(unassigned_count)

    # 4. Estimated emissions saved (kg)
    # Formula: idle_hours_avoided * vessel_size_teu * DEMURRAGE_RATE_PER_TEU_HOUR
    max_wait = float(get_settings().app.max_berth_wait_hours)
    total_emissions_saved = 0.0
    for a in assignments:
        wait = float(a.get("wait_hours", 0.0))
        size = int(a.get("size_teu", 6500))
        idle_hours_avoided = max(0.0, max_wait - wait)
        total_emissions_saved += idle_hours_avoided * size * DEMURRAGE_RATE_PER_TEU_HOUR

    estimated_emissions_saved_kg = round(total_emissions_saved, 1)

    return {
        "avg_wait_hours": avg_wait_hours,
        "berth_utilization_pct": min(100.0, berth_utilization_pct),
        "vessels_at_risk": vessels_at_risk,
        "estimated_emissions_saved_kg": estimated_emissions_saved_kg,
    }
