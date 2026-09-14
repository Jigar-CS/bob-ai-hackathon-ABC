"""Operations summary — one short paragraph for the shift supervisor.

Makes a single watsonx.ai call with the full ops plan; if the model is
unavailable or returns nothing usable, a templated fallback is produced
instead. The caller never receives a 500 from this module.
"""

from __future__ import annotations

import logging
from typing import Any

from portpulse.integrations.watsonx import WatsonxClient, WatsonxError, get_client

logger = logging.getLogger(__name__)


def _build_summary_prompt(plan: dict[str, Any]) -> str:
    forecast = plan.get("congestion_forecast", [])
    reroutes = plan.get("reroute_suggestions", [])
    assignments = plan.get("berth_assignments", [])
    unassigned_count = plan.get("unassigned_count", len(reroutes))

    high_days = [
        f"Day {d['day']} ({d['vessel_count']} vessels)"
        for d in forecast
        if d.get("risk_level") == "HIGH"
    ]
    medium_days = [f"Day {d['day']}" for d in forecast if d.get("risk_level") == "MEDIUM"]

    top_reroute = reroutes[0] if reroutes else None
    top_reroute_line = ""
    if top_reroute:
        alts = ", ".join(a["port"] for a in top_reroute.get("alternatives", []))
        top_reroute_line = (
            f"Most urgent unassigned vessel: {top_reroute.get('vessel_name', 'Unknown')} "
            f"(alternatives: {alts or 'none found'})."
        )

    priority1 = [a for a in assignments if str(a.get("priority", "")) == "1"]

    return (
        "You are a port shift supervisor assistant. Write a 3-4 sentence plain-language "
        "operations summary for the incoming shift supervisor based on the data below. "
        "Be direct and specific — mention risk days, unassigned vessels, and priority actions.\n\n"
        f"Total vessels assigned to berths: {len(assignments)}\n"
        f"Unassigned vessels requiring rerouting: {unassigned_count}\n"
        f"HIGH-risk congestion windows: {', '.join(high_days) if high_days else 'none'}\n"
        f"MEDIUM-risk congestion windows: {', '.join(medium_days) if medium_days else 'none'}\n"
        f"Priority-1 vessels berthed: {len(priority1)}\n"
        f"{top_reroute_line}\n\n"
        "Write the summary now (3-4 sentences, plain English, no bullet points):\n"
    )


def _template_summary(plan: dict[str, Any]) -> str:
    """Fallback summary when the AI call is unavailable."""
    forecast = plan.get("congestion_forecast", [])
    reroutes = plan.get("reroute_suggestions", [])
    assignments = plan.get("berth_assignments", [])
    unassigned_count = plan.get("unassigned_count", len(reroutes))

    high_days = [str(d["day"]) for d in forecast if d.get("risk_level") == "HIGH"]
    risk_line = (
        f"Day{'s' if len(high_days) > 1 else ''} {', '.join(high_days)} "
        f"{'are' if len(high_days) > 1 else 'is'} at HIGH congestion risk."
        if high_days
        else "No HIGH-risk congestion windows in the current horizon."
    )
    reroute_line = (
        f"{unassigned_count} vessel{'s' if unassigned_count != 1 else ''} could not be berthed "
        f"and {'are' if unassigned_count != 1 else 'is'} recommended for rerouting."
        if unassigned_count
        else "All vessels have been assigned to berths."
    )
    v_suffix = "s" if len(assignments) != 1 else ""
    priority_line = (
        f"{len(assignments)} vessel{v_suffix} assigned across berths. "
        "Ensure crane availability for priority-1 cargo."
    )
    return f"{risk_line} {reroute_line} {priority_line}"


def generate_ops_summary(
    plan: dict[str, Any],
    *,
    client: WatsonxClient | None = None,
) -> dict[str, object]:
    """Return a short plain-language summary of the ops plan.

    Never raises — falls back to a templated summary on any AI failure.
    """
    active_client: WatsonxClient = client if client is not None else get_client()

    if active_client.enabled:
        try:
            prompt = _build_summary_prompt(plan)
            text = active_client.generate_text(prompt)
            if text and text.strip():
                return {"summary": text.strip(), "ai_generated": True}
        except WatsonxError as err:
            logger.warning("watsonx.ai summary unavailable (%s) — using template.", err)
        except Exception:
            logger.exception("Unexpected error generating ops summary — using template.")

    return {"summary": _template_summary(plan), "ai_generated": False}
