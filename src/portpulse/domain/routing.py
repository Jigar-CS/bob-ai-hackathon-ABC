"""Alternate routing — "this ship could not get a berth, where else can it go?"

Candidate ports come from the alternate-port catalogue and are ranked by spare
capacity fit, then distance. IBM watsonx.ai turns the ranking into a short
natural-language recommendation; if the model is unconfigured, unreachable, or
returns something unparseable, structured template text is used instead. The
plan is never blocked by the LLM.

Fan-out is bounded twice over: a worker cap (``PORTPULSE_ROUTING_MAX_WORKERS``)
and a per-request call budget (``PORTPULSE_ROUTING_MAX_LLM_CALLS``).
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from portpulse.config import get_settings
from portpulse.csv_io import Row
from portpulse.datasets import load_alternate_ports
from portpulse.integrations.watsonx import (
    WatsonxClient,
    WatsonxError,
    get_client,
)

logger = logging.getLogger(__name__)

DEFAULT_REASON_UNASSIGNED = "No berth had capacity or availability within the 72-hour window"
MAX_ALTERNATIVES = 2

#: Vessel-supplied text is interpolated into the prompt, so it is length-capped and
#: stripped of newlines and control characters to limit prompt-injection surface.
_MAX_PROMPT_FIELD_LEN = 80
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_UNKNOWN_TOKENS = frozenset({"", "unknown", "n/a", "none", "null"})


def _sanitise(value: object, *, max_len: int = _MAX_PROMPT_FIELD_LEN) -> str:
    """Flatten an untrusted field into a single short line safe to interpolate."""
    text = _CONTROL_CHARS.sub(" ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def has_promptable_fields(vessel: Row) -> bool:
    """Whether a vessel has enough clean data to justify spending an LLM call."""
    for field in ("vessel_id", "name", "cargo_type"):
        value = str(vessel.get(field, "")).strip().lower()
        if value in _UNKNOWN_TOKENS:
            return False

    raw_size = str(vessel.get("size_teu", "")).strip()
    if raw_size.lower() in _UNKNOWN_TOKENS:
        return False
    try:
        return int(raw_size) > 0
    except ValueError:
        return False


def build_prompt(vessel: Row, candidates: list[dict[str, Any]]) -> str:
    """Build the routing-recommendation prompt for one vessel."""
    ports_summary = "\n".join(
        f"{index}. {port['port']}: {port['distance_km']}km away, "
        f"{port['spare_capacity_teu']:,} TEU spare capacity"
        for index, port in enumerate(candidates, start=1)
    )
    return (
        "You are a port operations planner. Recommend where to reroute a vessel.\n\n"
        "Vessel details:\n"
        f"- Name: {_sanitise(vessel.get('name'))}\n"
        f"- Size: {_sanitise(vessel.get('size_teu'), max_len=12)} TEU\n"
        f"- Cargo type: {_sanitise(vessel.get('cargo_type'))}\n"
        f"- Priority: {_sanitise(vessel.get('priority'), max_len=8) or 'unspecified'}\n"
        f"- Situation: {DEFAULT_REASON_UNASSIGNED}.\n\n"
        f"Candidate alternate ports:\n{ports_summary}\n\n"
        "Reply with exactly two sentences and nothing else.\n"
        "Sentence 1: state why the vessel could not be berthed here.\n"
        "Sentence 2: name the best candidate port and justify it using distance and capacity.\n"
    )


def parse_llm_response(text: str) -> tuple[str | None, str | None]:
    """Split a model reply into ``(reason_unassigned, recommendation)``.

    Tolerates prose, bulleted lists and numbered lists. Returns ``(None, None)``
    when nothing usable can be extracted, which triggers the template fallback.
    """
    if not text or not text.strip():
        return None, None

    sentences: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        without_marker = re.sub(r"^(?:\d+[.)]|[-*•])\s*", "", stripped)
        if not without_marker:
            continue
        sentences.extend(
            part.strip() for part in re.split(r"(?<=[.!?])\s+", without_marker) if part.strip()
        )

    if not sentences:
        return None, None
    recommendation = " ".join(sentences[1:]) if len(sentences) > 1 else None
    return sentences[0], recommendation


def _rank_candidates(vessel: Row, ports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ports that can take the vessel, nearest first; falls back to all ports."""
    try:
        size = int(str(vessel.get("size_teu", "0")).strip())
    except ValueError:
        size = 0

    fitting = [port for port in ports if port["spare_capacity_teu"] >= size] if size > 0 else []
    ranked = sorted(fitting or ports, key=lambda port: port["distance_km"])
    return ranked[:MAX_ALTERNATIVES]


def _template_reason(port: dict[str, Any]) -> str:
    return f"{port['spare_capacity_teu']:,} TEU spare capacity, {port['distance_km']}km away"


def _suggest_for_vessel(
    vessel: Row,
    ports: list[dict[str, Any]],
    client: WatsonxClient | None,
) -> dict[str, Any]:
    """Produce one reroute suggestion, degrading to template text on any failure."""
    vessel_id = str(vessel.get("vessel_id") or "UNKNOWN")
    vessel_name = str(vessel.get("name") or "Unknown Vessel")
    candidates = _rank_candidates(vessel, ports)

    reason_unassigned = DEFAULT_REASON_UNASSIGNED
    recommendation: str | None = None
    ai_generated = False

    if client is not None and candidates and has_promptable_fields(vessel):
        try:
            reply = client.generate_text(build_prompt(vessel, candidates))
            parsed_reason, parsed_recommendation = parse_llm_response(reply)
            if parsed_reason:
                reason_unassigned = parsed_reason
            if parsed_recommendation:
                recommendation = parsed_recommendation
                ai_generated = True
        except WatsonxError as err:
            logger.warning(
                "watsonx.ai reasoning unavailable for vessel %s (%s) — using template text.",
                vessel_id,
                err,
            )
        except Exception:
            logger.exception(
                "Unexpected error generating routing text for vessel %s — using template text.",
                vessel_id,
            )

    alternatives = [
        {
            "port": port["port"],
            "distance_km": port["distance_km"],
            "spare_capacity_teu": port["spare_capacity_teu"],
            "reason": recommendation if index == 0 and recommendation else _template_reason(port),
        }
        for index, port in enumerate(candidates)
    ]

    return {
        "vessel_id": vessel_id,
        "vessel_name": vessel_name,
        "reason_unassigned": reason_unassigned,
        "ai_generated": ai_generated,
        "alternatives": alternatives,
    }


def suggest_alternates(
    unassigned_vessels: list[Row],
    *,
    client: WatsonxClient | None = None,
    max_workers: int | None = None,
    max_llm_calls: int | None = None,
) -> list[dict[str, Any]]:
    """Recommend alternate ports for every unassigned vessel.

    Args:
        unassigned_vessels: Vessels that could not be berthed.
        client: watsonx client to use; defaults to the shared one. Pass ``None``
            explicitly via ``max_llm_calls=0`` to force template-only output.
        max_workers: Thread-pool size cap.
        max_llm_calls: Ceiling on LLM calls for this request; vessels beyond the
            budget get template text.

    Returns:
        One suggestion dict per vessel, in the input order.
    """
    if not unassigned_vessels:
        return []

    settings = get_settings().app
    workers = settings.routing_max_workers if max_workers is None else max_workers
    budget = settings.routing_max_llm_calls if max_llm_calls is None else max_llm_calls

    ports = load_alternate_ports()
    active_client = client if client is not None else get_client()
    if not active_client.enabled:
        logger.info(
            "watsonx.ai is not configured — routing recommendations will use template text."
        )
        active_client = None  # type: ignore[assignment]

    if active_client is not None and budget < len(unassigned_vessels):
        logger.info(
            "LLM call budget is %d for %d unassigned vessels; the remainder use template text.",
            budget,
            len(unassigned_vessels),
        )

    jobs = [
        (vessel, ports, active_client if index < budget else None)
        for index, vessel in enumerate(unassigned_vessels)
    ]

    if active_client is None or len(jobs) == 1:
        # No network work to parallelise, or nothing to gain from a pool.
        return [_suggest_for_vessel(*job) for job in jobs]

    with ThreadPoolExecutor(
        max_workers=min(workers, len(jobs)), thread_name_prefix="portpulse-routing"
    ) as executor:
        return list(executor.map(lambda job: _suggest_for_vessel(*job), jobs))
