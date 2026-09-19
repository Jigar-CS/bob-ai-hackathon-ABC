"""Berth and crane assignment — "which vessel goes to which berth, and when?"

A priority-first greedy allocator:

1. Sort vessels by priority (1 = highest), then by ETA.
2. For each vessel, pick the berth with sufficient capacity that frees up
   earliest, provided the resulting queue wait stays within the configured
   maximum.
3. Mark that berth busy until ``berth_start + avg_dwell_hours``.
4. Anything that cannot be placed is returned as unassigned, which is what
   feeds the alternate-routing engine.

Greedy rather than a full linear program: it is fast, deterministic, and every
decision carries a one-line explanation a shift supervisor can audit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from portpulse.config import get_settings
from portpulse.constants import ETA_FORMAT
from portpulse.csv_io import Row, parse_eta
from portpulse.errors import PlanningError

logger = logging.getLogger(__name__)


def _is_cargo_compatible(vessel_cargo: str | None, berth_allowed: str | None) -> bool:
    """Return True if berth permits vessel's cargo_type."""
    if not berth_allowed or not str(berth_allowed).strip():
        return True

    b_tokens = {
        t.strip().lower() for t in str(berth_allowed).replace(";", ",").split(",") if t.strip()
    }
    if not b_tokens or "all" in b_tokens or "any" in b_tokens or "*" in b_tokens:
        return True

    v_cargo = str(vessel_cargo or "general").strip().lower()
    return v_cargo in b_tokens


@dataclass(slots=True)
class _Berth:
    berth_id: str
    capacity_teu: int
    avg_dwell_hours: float
    crane_count: int | None
    free_at: datetime
    allowed_cargo_types: str = "all"


@dataclass(slots=True)
class _Vessel:
    row: Row
    vessel_id: str
    name: str
    eta: datetime
    size_teu: int
    priority: int | None
    cargo_type: str = "general"
    weather_delay_hours: float = 0.0
    weather_severity: str = "none"


@dataclass(slots=True)
class AssignmentResult:
    """Outcome of one assignment run."""

    assigned: list[dict[str, object]]
    unassigned: list[Row]


def _to_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _effective_dwell_hours(
    avg_dwell_hours: float,
    crane_count: int | None,
    baseline_crane_count: int,
    min_multiplier: float,
    max_multiplier: float,
) -> float:
    """Scale dwell time by crane availability relative to baseline.

    More cranes than baseline shortens dwell time; fewer lengthens it.
    Falls back to avg_dwell_hours unchanged when crane_count is missing
    or non-positive (unknown crane data should not silently distort
    the schedule).
    """
    if crane_count is None or crane_count <= 0:
        return avg_dwell_hours

    raw_multiplier = baseline_crane_count / crane_count
    multiplier = max(min_multiplier, min(max_multiplier, raw_multiplier))
    return avg_dwell_hours * multiplier


def _parse_berths(berths: list[Row]) -> list[_Berth]:
    parsed: list[_Berth] = []
    for berth in berths:
        try:
            parsed.append(
                _Berth(
                    berth_id=str(berth["berth_id"]),
                    capacity_teu=int(berth["capacity_teu"]),
                    avg_dwell_hours=float(berth["avg_dwell_hours"]),
                    crane_count=_to_int(berth.get("crane_count")),
                    free_at=datetime.min,
                    allowed_cargo_types=str(berth.get("allowed_cargo_types") or "all").strip(),
                )
            )
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Skipping berth with unusable data: %r (%s)", berth, err)
    return parsed


def _parse_vessels(vessels: list[Row]) -> tuple[list[_Vessel], list[Row]]:
    parsed: list[_Vessel] = []
    rejected: list[Row] = []
    for vessel in vessels:
        try:
            eta = parse_eta(vessel.get("eta"))
            size_teu = int(vessel["size_teu"])
            if size_teu <= 0:
                raise ValueError("size_teu must be positive")
        except (KeyError, TypeError, ValueError) as err:
            logger.warning(
                "Vessel %s has an unusable ETA or size (%s) — marking unassigned.",
                vessel.get("vessel_id", "?"),
                err,
            )
            rejected.append(vessel)
            continue

        raw_priority = _to_int(vessel.get("priority"))
        if raw_priority is not None:
            # Clamp priority to valid range [1, 5] so negative numbers can't jump the queue
            raw_priority = max(1, min(5, raw_priority))

        try:
            w_delay = float(vessel.get("weather_delay_hours") or 0.0)
        except (TypeError, ValueError):
            w_delay = 0.0
        w_sev = str(vessel.get("weather_severity") or "none")
        v_cargo = str(vessel.get("cargo_type") or "general").strip()

        parsed.append(
            _Vessel(
                row=vessel,
                vessel_id=str(vessel.get("vessel_id") or "UNKNOWN"),
                name=str(vessel.get("name") or "Unknown Vessel"),
                eta=eta,
                size_teu=size_teu,
                priority=raw_priority,
                cargo_type=v_cargo,
                weather_delay_hours=w_delay,
                weather_severity=w_sev,
            )
        )
    return parsed, rejected


def _ml_berth_score(
    vessel: "_Vessel",
    berth: "_Berth",
    n_berths: int,
    n_vessels: int,
) -> float:
    """Return ML-predicted wait hours for vessel at berth; fallback to infinity."""
    try:
        from portpulse.ml.predictor import predict_wait

        b_cranes = berth.crane_count if berth.crane_count and berth.crane_count > 0 else 2
        v_prio = vessel.priority if vessel.priority is not None else 2
        result = predict_wait(
            {
                "size_teu": vessel.size_teu,
                "priority": v_prio,
                "crane_count": b_cranes,
                "berth_capacity_teu": berth.capacity_teu,
                "n_berths": n_berths,
                "n_vessels": n_vessels,
            }
        )
        return float(result) if result is not None else float("inf")
    except Exception:
        return float("inf")


def assign_berths(
    vessels: list[Row],
    berths: list[Row],
    *,
    max_wait_hours: float | None = None,
) -> AssignmentResult:
    """Allocate vessels to berths.

    When ``PORTPULSE_ML_ENABLED=true``, berth selection is ML-first:
    every eligible berth is scored with the wait-time regressor and the
    berth with the lowest predicted wait is preferred over the one with
    the earliest free slot.  Rule-based earliest-slot selection is the
    fallback when ML is disabled or all model calls fail.

    Args:
        vessels: Vessel rows with ``vessel_id``, ``name``, ``eta``, ``size_teu``, ``priority``.
        berths: Berth rows with ``berth_id``, ``capacity_teu``, ``crane_count``,
            ``avg_dwell_hours``.
        max_wait_hours: Queue tolerance; defaults to ``PORTPULSE_MAX_BERTH_WAIT_HOURS``.

    Returns:
        An :class:`AssignmentResult` with assignment records and unplaced vessel rows.

    Raises:
        PlanningError: if no usable berths are supplied.
    """
    app_settings = get_settings().app
    limit = app_settings.max_berth_wait_hours if max_wait_hours is None else max_wait_hours
    baseline_cranes = app_settings.baseline_crane_count
    min_mult = app_settings.crane_dwell_min_multiplier
    max_mult = app_settings.crane_dwell_max_multiplier
    use_ml = app_settings.ml_enabled

    if not berths:
        raise PlanningError("At least one berth is required to assign vessels.")

    available = _parse_berths(berths)
    if not available:
        raise PlanningError("No berth rows were usable — check the berth dataset.")

    if not vessels:
        return AssignmentResult(assigned=[], unassigned=[])

    parsed_vessels, unassigned = _parse_vessels(vessels)
    # Priority ascending (1 first), unknown priority last, then weather-adjusted arrival time.
    parsed_vessels.sort(
        key=lambda v: (
            v.priority if v.priority is not None else 99,
            v.eta + timedelta(hours=v.weather_delay_hours),
        )
    )

    assigned: list[dict[str, object]] = []
    berth_queues: dict[str, list[dict[str, object]]] = {b.berth_id: [] for b in available}

    for vessel in parsed_vessels:
        best: _Berth | None = None
        best_start: datetime | None = None
        best_wait = 0.0
        best_ml_score: float = float("inf")

        for berth in available:
            if vessel.size_teu > berth.capacity_teu:
                continue
            if not _is_cargo_compatible(vessel.cargo_type, berth.allowed_cargo_types):
                continue
            v_arrival = vessel.eta + timedelta(hours=vessel.weather_delay_hours)
            start_time = max(v_arrival, berth.free_at)
            wait_hours = (start_time - vessel.eta).total_seconds() / 3600.0
            if wait_hours > limit:
                continue

            if use_ml:
                # ML-first: pick the berth with the lowest predicted wait time.
                ml_score = _ml_berth_score(vessel, berth, len(available), len(parsed_vessels))
                if ml_score < best_ml_score or (
                    ml_score == best_ml_score and (best_start is None or start_time < best_start)
                ):
                    best, best_start, best_wait = berth, start_time, wait_hours
                    best_ml_score = ml_score
            else:
                # Rule-based: pick berth with earliest free slot.
                if best_start is None or start_time < best_start:
                    best, best_start, best_wait = berth, start_time, wait_hours

        if best is None or best_start is None:
            unassigned.append(vessel.row)
            continue

        effective_dwell = _effective_dwell_hours(
            best.avg_dwell_hours,
            best.crane_count,
            baseline_cranes,
            min_mult,
            max_mult,
        )
        departure = best_start + timedelta(hours=effective_dwell)
        best.free_at = departure

        # Queue tracking
        queue = berth_queues[best.berth_id]
        queue_position = len(queue)
        if queue_position == 0:
            queue_status = "BERTHED"
            queued_behind = None
        else:
            queue_status = f"QUEUED (#{queue_position})"
            queued_behind = str(queue[-1]["vessel_name"])

        queue.append({
            "vessel_id": vessel.vessel_id,
            "vessel_name": vessel.name,
            "berth_start": best_start,
            "departure": departure,
        })

        priority_label = f"P{vessel.priority}" if vessel.priority is not None else "unprioritised"
        cargo_note = (
            f" handling '{vessel.cargo_type}'"
            if best.allowed_cargo_types and best.allowed_cargo_types.lower() not in ("all", "any", "*")
            else ""
        )
        if best_wait == 0:
            reason = f"{priority_label}, fits {best.berth_id} capacity{cargo_note}, berth free on arrival"
        else:
            reason = f"{priority_label}, queued {best_wait:.1f}h for berth {best.berth_id}{cargo_note}"

        if queue_position > 0 and queued_behind:
            reason += f"; queued #{queue_position} behind {queued_behind}"
        if vessel.weather_delay_hours > 0:
            reason += f" (+{vessel.weather_delay_hours:.1f}h weather delay)"

        multiplier = effective_dwell / best.avg_dwell_hours if best.avg_dwell_hours > 0 else 1.0
        if best.crane_count is not None and best.crane_count > 0 and abs(multiplier - 1.0) > 0.01:
            reason += f", {best.crane_count} cranes ({multiplier:.2f}x baseline dwell)"

        pred_wait: float | None = None
        pred_demurrage: float | None = None
        pred_moves: float | None = None
        anomalous: bool | None = None

        if app_settings.ml_enabled:
            try:
                from portpulse.ml.predictor import (
                    is_anomalous,
                    predict_crane_productivity,
                    predict_demurrage_cost,
                    predict_wait,
                )

                v_prio = vessel.priority if vessel.priority is not None else 2
                b_cranes = (
                    best.crane_count if best.crane_count is not None and best.crane_count > 0 else 2
                )
                is_hazmat = 1 if str(vessel.row.get("cargo_type", "")).lower() == "hazmat" else 0

                pred_wait = predict_wait(
                    {
                        "size_teu": vessel.size_teu,
                        "priority": v_prio,
                        "crane_count": b_cranes,
                        "berth_capacity_teu": best.capacity_teu,
                        "n_berths": len(available),
                        "n_vessels": len(parsed_vessels),
                    }
                )

                pred_demurrage = predict_demurrage_cost(
                    {
                        "wait_hours": best_wait,
                        "priority": v_prio,
                        "size_teu": vessel.size_teu,
                        "cargo_type_hazmat": is_hazmat,
                    }
                )

                pred_moves = predict_crane_productivity(
                    {
                        "crane_count": b_cranes,
                        "size_teu": vessel.size_teu,
                        "priority": v_prio,
                        "berth_capacity_teu": best.capacity_teu,
                    }
                )

                anomalous = is_anomalous(
                    {
                        "size_teu": vessel.size_teu,
                        "effective_dwell_hours": effective_dwell,
                        "wait_hours": best_wait,
                        "crane_count": b_cranes,
                        "priority": v_prio,
                    }
                )
            except Exception as err:
                logger.warning("ML vessel prediction failed for %s: %s", vessel.vessel_id, err)

        assigned.append(
            {
                "vessel_id": vessel.vessel_id,
                "vessel_name": vessel.name,
                "berth_id": best.berth_id,
                "crane_count": best.crane_count,
                "effective_dwell_hours": round(effective_dwell, 2),
                "arrival": vessel.eta.strftime(ETA_FORMAT),
                "berth_start": best_start.strftime(ETA_FORMAT),
                "departure_est": departure.strftime(ETA_FORMAT),
                "wait_hours": round(best_wait, 1),
                "priority": vessel.priority,
                "size_teu": vessel.size_teu,
                "queue_position": queue_position,
                "queue_status": queue_status,
                "queued_behind": queued_behind,
                "reason": reason,
                "predicted_wait_hours": pred_wait,
                "predicted_demurrage_cost_usd": pred_demurrage,
                "predicted_moves_per_hour": pred_moves,
                "is_anomalous": anomalous,
                "origin_port": vessel.row.get("origin_port"),
                "origin_lat": vessel.row.get("origin_lat"),
                "origin_lon": vessel.row.get("origin_lon"),
                "dest_port": vessel.row.get("dest_port"),
                "dest_lat": vessel.row.get("dest_lat"),
                "dest_lon": vessel.row.get("dest_lon"),
                "weather_delay_hours": vessel.weather_delay_hours,
                "weather_severity": vessel.weather_severity,
            }
        )

    return AssignmentResult(assigned=assigned, unassigned=unassigned)
