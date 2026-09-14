"""Conversational chat — a shift supervisor can ask plain-English questions
about the live ops plan and get a grounded answer.

One watsonx.ai call per message. The full plan is summarised into a compact
context block so the model has the facts it needs without token bloat. If
watsonx is unconfigured the response degrades to an intelligent domain reply
rather than a generic error.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from portpulse.integrations.watsonx import WatsonxClient, WatsonxError, get_client

logger = logging.getLogger(__name__)

_MAX_HISTORY = 6  # message pairs kept for context (3 turns)
_MAX_USER_MSG_LEN = 1000  # max length of user question
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

_SCOPE_REJECTION = (
    "I am PortPulse Assistant, dedicated exclusively to PortPulse port operations, "
    "vessel allocations, congestion forecasting, and alternate berth routing. "
    "I cannot answer questions outside of this domain."
)


def _sanitise(text: str, max_len: int = _MAX_USER_MSG_LEN) -> str:
    text = _CONTROL_CHARS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _plan_context(plan: dict[str, Any]) -> str:
    """Produce a compact, token-efficient summary of the ops plan for the prompt."""
    forecast = plan.get("congestion_forecast") or []
    assignments = plan.get("berth_assignments") or []
    reroutes = plan.get("reroute_suggestions") or []
    unassigned_count = plan.get("unassigned_count", len(reroutes))
    warnings = plan.get("warnings") or []

    # Forecast lines
    fc_lines = []
    for w in forecast:
        fc_lines.append(
            f"  Day {w.get('day', '?')}: {w.get('risk_level', '?')} risk, "
            f"{w.get('vessel_count', 0)} vessels, {w.get('incoming_teu', 0):,} TEU inbound "
            f"({w.get('window_start', '')} - {w.get('window_end', '')})"
        )
    fc_block = "\n".join(fc_lines) if fc_lines else "  No forecast windows."

    # Assignment summary — list every row so vessel-specific questions work
    assign_lines = []
    for a in assignments:
        assign_lines.append(
            f"  {a.get('vessel_name', '?')} (ID:{a.get('vessel_id', '?')}) "
            f"-> Berth {a.get('berth_id', '?')}, "
            f"arrival {a.get('arrival', '?')}, start {a.get('berth_start', '?')}, "
            f"departs {a.get('departure_est', '?')}, wait {a.get('wait_hours', 0)}h, "
            f"P{a.get('priority', '?')}, cranes:{a.get('crane_count', '?')}"
        )
    assign_block = "\n".join(assign_lines) if assign_lines else "  None."

    # Reroute summary
    reroute_lines = []
    for r in reroutes:
        alts = ", ".join(
            f"{a.get('port', '?')} ({a.get('distance_km', '?')}km)"
            for a in (r.get("alternatives") or [])
        )
        v_label = f"{r.get('vessel_name', '?')} (ID:{r.get('vessel_id', '?')})"
        v_reason = r.get("reason_unassigned", "overflow")
        reroute_lines.append(
            f"  {v_label} - unassigned - reason: {v_reason} - alternatives: {alts or 'none'}"
        )
    reroute_block = "\n".join(reroute_lines) if reroute_lines else "  None."

    warn_block = "\n".join(f"  {w}" for w in warnings) if warnings else "  None."

    return (
        f"=== CONGESTION FORECAST ===\n{fc_block}\n\n"
        f"=== BERTH ASSIGNMENTS ({len(assignments)} vessels) ===\n{assign_block}\n\n"
        f"=== UNASSIGNED / REROUTED ({unassigned_count} vessels) ===\n{reroute_block}\n\n"
        f"=== WARNINGS ===\n{warn_block}"
    )


def _build_prompt(
    user_message: str,
    plan: dict[str, Any],
    history: list[dict[str, str]],
) -> str:
    context = _plan_context(plan)

    # Build conversation history block (newest last)
    history_block = ""
    if history:
        lines = []
        for turn in history[-_MAX_HISTORY:]:
            role = turn.get("role", "user")
            content = _sanitise(turn.get("content", ""), max_len=1500)
            lines.append(f"{'Supervisor' if role == 'user' else 'Assistant'}: {content}")
        history_block = "\n".join(lines) + "\n"

    return (
        "System Instruction: You are PortPulse Assistant, an expert AI assistant "
        "dedicated EXCLUSIVELY to PortPulse container port operations, 72-hour berth "
        "allocation planning, vessel scheduling, container congestion prediction, "
        "and alternate port rerouting.\n\n"
        "STRICT DOMAIN BOUNDARIES & SCOPE GUARDRAILS:\n"
        "1. ONLY answer questions directly related to PortPulse port operations, live "
        "ops plan data, vessel berth assignments, crane allocations, arrival/departure "
        "schedules, priority queues, congestion forecasts, unassigned/rerouted ships, "
        "and candidate alternate ports.\n"
        "2. IF THE USER ASKS ANYTHING OUTSIDE THIS SCOPE (such as general knowledge, "
        "trivia, weather outside ports, coding in other languages, entertainment, sports, "
        "recipes, history, personal advice, etc.), YOU MUST STRICTLY REFUSE TO ANSWER. "
        "Reply with: 'I am PortPulse Assistant, dedicated exclusively to PortPulse port "
        "operations, vessel allocations, congestion forecasting, and alternate berth routing. "
        "I cannot answer questions outside of this domain.'\n"
        "3. Provide advanced, thorough, structured, and highly detailed analytical answers. "
        "Use clear markdown formatting (bullet points, bold highlights, operational metrics, "
        "and step-by-step reasoning). Provide comprehensive explanations grounded strictly "
        "in the LIVE OPS PLAN DATA provided below. Never make up facts not present in the data.\n\n"
        f"--- LIVE OPS PLAN DATA ---\n{context}\n--- END OF DATA ---\n\n"
        f"{history_block}"
        f"Supervisor: {_sanitise(user_message)}\n"
        "Assistant:"
    )


def _fallback_reply(user_message: str, plan: dict[str, Any]) -> str:
    """Advanced, highly detailed domain reply when watsonx.ai is not active."""
    msg = user_message.lower()
    forecast = plan.get("congestion_forecast") or []
    assignments = plan.get("berth_assignments") or []
    reroutes = plan.get("reroute_suggestions") or []

    # Out of domain / scope check
    out_of_scope_keywords = (
        "weather",
        "sports",
        "recipe",
        "python",
        "javascript",
        "code",
        "movie",
        "song",
        "president",
        "capital of",
        "fibonacci",
        "game",
        "who won",
        "joke",
        "story",
        "math",
        "politics",
        "travel advice",
        "restaurant",
    )
    port_keywords = (
        "vessel",
        "ship",
        "berth",
        "port",
        "congestion",
        "routing",
        "reroute",
        "allocation",
        "teu",
        "horizon",
        "plan",
        "forecast",
        "schedule",
        "crane",
        "dwell",
        "cargo",
        "hazmat",
        "reefer",
        "p1",
        "p2",
        "p3",
        "priority",
        "portpulse",
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "b6",
    )

    is_out_of_scope = any(kw in msg for kw in out_of_scope_keywords) and not any(
        kw in msg for kw in port_keywords
    )
    if is_out_of_scope:
        return _SCOPE_REJECTION

    # 1. Search for specific vessel query (e.g. V101, MV Pacific Titan, V108...)
    for a in assignments:
        vid = str(a.get("vessel_id", "")).lower().strip()
        vname = str(a.get("vessel_name", "")).lower().strip()
        if (vid and re.search(r"\b" + re.escape(vid) + r"\b", msg)) or (vname and vname in msg):
            return (
                f"### Vessel Operations Report: {a.get('vessel_name')} ({a.get('vessel_id')})\n"
                f"- **Status**: Berthed at **Berth {a.get('berth_id')}**\n"
                f"- **Priority Level**: P{a.get('priority')} (1 = Highest Priority)\n"
                f"- **Cranes Allocated**: {a.get('crane_count', 'Standard')} cranes\n"
                f"- **Arrival Time (ETA)**: `{a.get('arrival')}`\n"
                f"- **Berth Start Time**: `{a.get('berth_start')}`\n"
                f"- **Estimated Departure**: `{a.get('departure_est')}`\n"
                f"- **Queue Wait Duration**: `{a.get('wait_hours')} hours`\n"
                f"- **Allocation Rationale**: {a.get('reason')}"
            )

    for r in reroutes:
        vid = str(r.get("vessel_id", "")).lower().strip()
        vname = str(r.get("vessel_name", "")).lower().strip()
        if (vid and re.search(r"\b" + re.escape(vid) + r"\b", msg)) or (vname and vname in msg):
            alts_formatted = "\n".join(
                f"  - **{alt.get('port')}**: {alt.get('distance_km')} km away "
                f"({alt.get('spare_capacity_teu', alt.get('spare_capacity', 0)):,} TEU spare)"
                for alt in (r.get("alternatives") or [])
            )
            reason = r.get("reason_unassigned", "Exceeds maximum berth capacity or wait time limit")
            return (
                f"### Rerouting Analysis: {r.get('vessel_name')} ({r.get('vessel_id')})\n"
                f"- **Status**: Unassigned / Pushed to Rerouting Queue\n"
                f"- **Primary Reason**: {reason}\n"
                f"- **Candidate Alternate Ports**:\n{alts_formatted or '  - None available'}\n"
                f"- **Recommendation**: Divert vessel to top alternate port matching cargo "
                f"handling and draft capacity."
            )

    # 2. Search for specific berth query (e.g., B1, B2, B3...)
    berth_match = re.search(r"\b(b[1-6])\b", msg)
    if berth_match:
        target_berth = berth_match.group(1).upper()
        berth_vessels = [a for a in assignments if a.get("berth_id") == target_berth]
        if berth_vessels:
            v_rows = "\n".join(
                f"- **{a.get('vessel_name')}** (ID: {a.get('vessel_id')}, P{a.get('priority')}): "
                f"Arrives `{a.get('arrival')}` -> Start `{a.get('berth_start')}` -> "
                f"Departs `{a.get('departure_est')}` (Wait: {a.get('wait_hours')}h)"
                for a in berth_vessels
            )
            return (
                f"### Berth Schedule & Capacity Report: Berth {target_berth}\n"
                f"- **Total Assigned Vessels**: {len(berth_vessels)} vessel(s)\n"
                f"- **Vessel Queue & Operations Breakdown**:\n{v_rows}\n"
                f"- **Summary**: Berth {target_berth} operating across 72-hour window."
            )
        return (
            f"### Berth Status: Berth {target_berth}\n"
            f"No vessels are currently scheduled for Berth {target_berth} in this 72-hour window."
        )

    # 3. Congestion / Risk / Forecast Queries
    if any(kw in msg for kw in ("high", "risk", "congestion", "forecast", "window")):
        fc_rows = []
        for w in forecast:
            in_teu = w.get("incoming_teu", 0)
            v_cnt = w.get("vessel_count", 0)
            fc_rows.append(
                f"- **Day {w.get('day')}** ({w.get('window_start')} to {w.get('window_end')}): "
                f"**{w.get('risk_level')} RISK** (Risk Ratio: `{w.get('risk_ratio')}`)\n"
                f"  - Incoming Volume: `{in_teu:,} TEU` ({v_cnt} vessels)\n"
                f"  - Total Berth Capacity: `{w.get('total_capacity_teu'):,} TEU`\n"
                f"  - Driver: {w.get('reason')}"
            )
        fc_block = "\n".join(fc_rows) if fc_rows else "- No forecast windows available."

        return (
            f"### 72-Hour Container Congestion & Risk Assessment\n\n"
            f"{fc_block}\n\n"
            f"#### Operations Planning Guidance:\n"
            f"- **High Risk**: Inbound cargo exceeds 85% of total berth throughput capacity.\n"
            f"- **Action Required**: Prioritize P1 vessels and divert overflow vessels."
        )

    # 4. Routing / Rerouting / Unassigned Queries
    if any(
        kw in msg
        for kw in (
            "routing",
            "reroute",
            "rerouted",
            "unassigned",
            "alternate",
            "cannot",
            "can't",
            "queue",
        )
    ):
        if reroutes:
            r_items = []
            for r in reroutes[:5]:
                top_alt = (r.get("alternatives") or [{}])[0].get("port", "N/A")
                dist = (r.get("alternatives") or [{}])[0].get("distance_km", "N/A")
                v_name = r.get("vessel_name")
                v_id = r.get("vessel_id")
                r_reason = r.get("reason_unassigned")
                r_items.append(
                    f"- **{v_name}** (ID: {v_id}) — Reason: *{r_reason}* -> "
                    f"Best Alternate: **{top_alt}** ({dist}km)"
                )
            r_block = "\n".join(r_items)
            more_str = (
                f"\n*...and {len(reroutes) - 5} more unassigned vessel(s).*"
                if len(reroutes) > 5
                else ""
            )
            return (
                f"### Alternate Routing & Rerouting Queue Detailed Analysis\n"
                f"- **Total Unassigned Vessels**: `{len(reroutes)}` vessel(s) in queue\n"
                f"- **Unassigned Vessel Roster**:\n{r_block}{more_str}\n\n"
                f"#### Alternate Port Catalogue:\n"
                f"- **Port of Ensenada**: 240 km away | 4,000 TEU spare capacity\n"
                f"- **Port of Oakland**: 620 km away | 9,000 TEU spare capacity\n"
                f"- **Port of Tacoma**: 1,450 km away | 14,000 TEU spare capacity\n"
                f"AI routing ranks ports by capacity fit, distance, and cargo capability."
            )
        return (
            "### Alternate Routing Analysis\n"
            "All vessels in the submitted schedule have been successfully allocated to berths "
            "within the maximum wait window. No vessels require alternate port rerouting."
        )

    # 5. Allocation & Assignment Queries
    if any(
        kw in msg
        for kw in (
            "assigned",
            "berth",
            "assignment",
            "allocate",
            "allocation",
            "priority",
            "schedule",
        )
    ):
        p1 = [a for a in assignments if a.get("priority") == 1]
        p2 = [a for a in assignments if a.get("priority") == 2]
        p3 = [a for a in assignments if a.get("priority") == 3]

        berth_counts: dict[str, int] = {}
        for a in assignments:
            bid = str(a.get("berth_id", "Unknown"))
            berth_counts[bid] = berth_counts.get(bid, 0) + 1
        b_summary = ", ".join(f"**{b}**: {c} vessels" for b, c in sorted(berth_counts.items()))

        return (
            f"### Detailed Berth Allocation Plan Summary\n"
            f"- **Total Berthed Vessels**: `{len(assignments)}` vessels\n"
            f"- **Priority Breakdown**:\n"
            f"  - **Priority 1 (Time-Critical)**: `{len(p1)}` vessel(s)\n"
            f"  - **Priority 2 (Standard)**: `{len(p2)}` vessel(s)\n"
            f"  - **Priority 3 (Flexible)**: `{len(p3)}` vessel(s)\n"
            f"- **Berth Distribution**: {b_summary or 'None'}\n"
            f"- **Scheduling Algorithm**: Priority-first greedy allocation placing vessels at "
            f"the earliest available berth meeting TEU capacity specifications."
        )

    # 6. Overview & Project Explanation
    if any(
        kw in msg
        for kw in ("summary", "overview", "status", "portpulse", "what is", "how does", "help")
    ):
        high_windows = [f"Day {w['day']}" for w in forecast if w.get("risk_level") == "HIGH"]
        high_str = (
            f"**HIGH RISK** alert on {', '.join(high_windows)}"
            if high_windows
            else "All windows at LOW/MEDIUM risk"
        )
        return (
            f"### PortPulse Operations Center Overview\n"
            f"- **Live Plan Status**: `{len(assignments)}` berthed, `{len(reroutes)}` unassigned.\n"
            f"- **Congestion Risk**: {high_str}.\n"
            f"- **Core Capabilities**:\n"
            f"  1. **72-Hour Berth Allocation**: Priority-based placement minimizing queue wait.\n"
            f"  2. **24-Hour Congestion Predictor**: Computes incoming TEU vs capacity ratio.\n"
            f"  3. **AI Alternate Routing**: Ranks alternate ports using watsonx.ai reasoning.\n\n"
            f"Ask me for detailed reports on any vessel, berth, or congestion window."
        )

    # Default fallback response for ambiguous port queries
    return (
        f"### PortPulse Live Operations Status\n"
        f"- **Berthed Vessels**: `{len(assignments)}` | "
        f"**Unassigned Vessels**: `{len(reroutes)}`\n"
        f"I am ready to provide detailed analytical reports on:\n"
        f"1. **Vessel Schedules & Allocations** (search by vessel ID or name)\n"
        f"2. **Berth Schedules & Capacity** (e.g. Berth B1-B6 status)\n"
        f"3. **Congestion Forecasts** (24-hour risk level breakdowns)\n"
        f"4. **Alternate Port Rerouting** (candidate port distance & capacity analysis)"
    )


def answer(
    user_message: str,
    plan: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    *,
    client: WatsonxClient | None = None,
) -> dict[str, object]:
    """Answer one supervisor question about the live plan.

    Args:
        user_message: The supervisor's free-text question.
        plan:         The current ops plan dict (same shape as OpsPlan).
        history:      Previous turns as ``[{"role": "user"|"assistant", "content": "..."}]``.
        client:       watsonx client; defaults to the shared singleton.

    Returns:
        ``{"reply": str, "ai_generated": bool}`` — never raises.
    """
    history = history or []
    active_client: WatsonxClient = client if client is not None else get_client()

    if active_client.enabled:
        try:
            prompt = _build_prompt(user_message, plan, history)
            raw = active_client.generate_text(prompt)
            # Strip any "Assistant:" prefix the model might echo back
            reply = re.sub(r"^[Aa]ssistant:\s*", "", raw).strip()
            if reply:
                return {"reply": reply, "ai_generated": True}
        except WatsonxError as err:
            logger.warning("watsonx.ai chat unavailable (%s) — using fallback.", err)
        except Exception:
            logger.exception("Unexpected error in chat — using fallback.")

    return {"reply": _fallback_reply(user_message, plan), "ai_generated": False}
