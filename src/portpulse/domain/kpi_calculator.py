"""KPI summary calculation module.

Computes high-level operations metrics (wait time, utilization, unassigned count,
and emissions savings) from existing plan data without modifying core algorithms.

When ML predictions are present on assignments, uses them for the avg_wait_hours
metric to reflect ML-expected waits rather than greedy-slot raw waits.
"""

from __future__ import annotations

import logging
from typing import Any

from portpulse.config import get_settings
from portpulse.constants import EMISSIONS_KG_PER_TEU_HOUR_ESTIMATE

logger = logging.getLogger(__name__)


def calculate_plan_kpis(plan: dict[str, Any]) -> dict[str, float | int]:
    """Calculate summary KPIs from plan data.

    When ML predictions (``predicted_wait_hours``, ``predicted_demurrage_cost_usd``)
    are present on assignments, they take priority over rule-based values for
    the avg_wait_hours and total_predicted_demurrage_usd metrics.

    Args:
        plan: The operations plan dictionary containing ``berth_assignments``,
            ``unassigned_count``, ``congestion_forecast``, and ``weather_summary``.

    Returns:
        Dict with keys: ``avg_wait_hours``, ``berth_utilization_pct``,
        ``vessels_at_risk``, ``estimated_emissions_saved_kg``,
        ``total_predicted_demurrage_usd``, ``weather_delayed_vessels``.
    """
    assignments = plan.get("berth_assignments") or []
    forecast = plan.get("congestion_forecast") or []
    unassigned_count = plan.get("unassigned_count", len(plan.get("reroute_suggestions") or []))
    weather_summary = plan.get("weather_summary") or []

    # 1. Average wait hours — prefer ML predicted wait when available
    if assignments:
        ml_waits = [
            float(a["predicted_wait_hours"])
            for a in assignments
            if a.get("predicted_wait_hours") is not None
        ]
        if ml_waits:
            avg_wait_hours = round(max(0.0, sum(ml_waits) / len(ml_waits)), 2)
        else:
            total_wait = sum(float(a.get("wait_hours", 0.0)) for a in assignments)
            avg_wait_hours = round(max(0.0, total_wait / len(assignments)), 2)
    else:
        avg_wait_hours = 0.0

    # 2. Berth utilization percentage
    total_assigned_teu = 0
    for a in assignments:
        size = a.get("size_teu")
        if size is not None:
            total_assigned_teu += int(size)
        else:
            logger.warning("Assignment missing size_teu for vessel %s", a.get("vessel_id"))

    single_window_capacity = max(
        (int(w.get("total_capacity_teu", 0)) for w in forecast), default=0
    )
    if single_window_capacity > 0:
        berth_utilization_pct = round((total_assigned_teu / single_window_capacity) * 100, 1)
    else:
        berth_utilization_pct = (
            round((total_assigned_teu / 90000) * 100, 1) if total_assigned_teu else 0.0
        )

    # 3. Vessels at risk (unassigned)
    vessels_at_risk = int(unassigned_count)

    # 4. Estimated emissions saved (kg)
    max_wait = float(get_settings().app.max_berth_wait_hours)
    total_emissions_saved = 0.0
    for a in assignments:
        wait = (
            float(a["predicted_wait_hours"])
            if a.get("predicted_wait_hours") is not None
            else float(a.get("wait_hours", 0.0))
        )
        size = int(a.get("size_teu", 0))
        if size > 0:
            idle_hours_avoided = max(0.0, max_wait - wait)
            total_emissions_saved += idle_hours_avoided * size * EMISSIONS_KG_PER_TEU_HOUR_ESTIMATE

    estimated_emissions_saved_kg = round(total_emissions_saved, 1)

    # 5. Total predicted demurrage (ML-based, USD) — sum across assignments
    total_predicted_demurrage_usd = round(
        sum(
            float(a["predicted_demurrage_cost_usd"])
            for a in assignments
            if a.get("predicted_demurrage_cost_usd") is not None
        ),
        2,
    )

    # 6. Weather-delayed vessel count
    weather_delayed_vessels = len(
        [e for e in weather_summary if float(e.get("delay_hours", 0)) > 0]
    )

    return {
        "avg_wait_hours": avg_wait_hours,
        "berth_utilization_pct": min(100.0, berth_utilization_pct),
        "vessels_at_risk": vessels_at_risk,
        "estimated_emissions_saved_kg": estimated_emissions_saved_kg,
        "total_predicted_demurrage_usd": total_predicted_demurrage_usd,
        "weather_delayed_vessels": weather_delayed_vessels,
    }
