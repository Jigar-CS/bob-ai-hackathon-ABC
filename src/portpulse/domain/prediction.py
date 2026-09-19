"""Congestion prediction — "which windows are going to exceed berth capacity?"

Incoming vessels are bucketed into rolling 24-hour windows starting at the
earliest ETA in the dataset. For each window the arriving cargo volume is
compared against total berth capacity to produce a risk ratio and level.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from portpulse.config import get_settings
from portpulse.constants import ETA_FORMAT, PLANNING_HORIZON_DAYS
from portpulse.csv_io import Row, parse_eta
from portpulse.errors import PlanningError

logger = logging.getLogger(__name__)

WINDOW_HOURS = 24


def _total_capacity(berths: list[Row]) -> int:
    total = 0
    for berth in berths:
        try:
            total += int(berth["capacity_teu"])
        except (KeyError, TypeError, ValueError) as err:
            logger.warning("Skipping berth with unusable capacity_teu: %r (%s)", berth, err)
    return total


def _parse_arrivals(vessels: list[Row]) -> list[tuple[datetime, int]]:
    arrivals: list[tuple[datetime, int]] = []
    for vessel in vessels:
        try:
            eta = parse_eta(vessel.get("eta"))
            size = int(vessel["size_teu"])
        except (KeyError, TypeError, ValueError) as err:
            logger.warning(
                "Skipping vessel %s with unusable eta/size_teu (%s)",
                vessel.get("vessel_id", "?"),
                err,
            )
            continue
        arrivals.append((eta, size))
    return arrivals


def predict_congestion(
    vessels: list[Row],
    berths: list[Row],
    *,
    horizon_days: int = PLANNING_HORIZON_DAYS,
    high_risk_ratio: float | None = None,
    medium_risk_ratio: float | None = None,
    now: datetime | None = None,
) -> list[dict[str, object]]:
    """Assess congestion risk per 24-hour window across the planning horizon.

    The horizon start is ``now`` when supplied explicitly (tests, or callers that
    want a wall-clock anchor).  When ``now`` is omitted the function uses the
    current system time **unless** all vessel ETAs lie entirely in the future
    beyond the 72-hour window — in that case the horizon is anchored to the
    earliest arriving vessel so that a future-dated dataset always produces a
    useful forecast instead of an empty one.

    Args:
        vessels: Vessel rows containing at least ``eta`` and ``size_teu``.
        berths: Berth rows containing at least ``capacity_teu``.
        horizon_days: Number of 24-hour windows to report.
        high_risk_ratio: Ratio above which a window is HIGH risk.
        medium_risk_ratio: Ratio above which a window is MEDIUM risk.
        now: Reference start time for horizon; defaults to current system time,
            with automatic fallback to earliest ETA for future-dated datasets.

    Returns:
        One dict per window, ordered by window index.

    Raises:
        PlanningError: if no usable vessel or berth rows are supplied.
    """
    settings = get_settings().app
    using_default_thresholds = high_risk_ratio is None and medium_risk_ratio is None
    high = settings.congestion_high_risk_ratio if high_risk_ratio is None else high_risk_ratio
    medium = (
        settings.congestion_medium_risk_ratio if medium_risk_ratio is None else medium_risk_ratio
    )

    if not vessels:
        raise PlanningError("At least one vessel is required to forecast congestion.")
    if not berths:
        raise PlanningError("At least one berth is required to forecast congestion.")

    total_capacity = _total_capacity(berths)
    if total_capacity <= 0:
        raise PlanningError("Total berth capacity is zero — check the berth dataset.")

    arrivals = _parse_arrivals(vessels)
    if not arrivals:
        raise PlanningError("No vessel rows had a usable ETA and size — cannot forecast.")

    if now is not None:
        # Explicit override (e.g. from tests or the planner's ``now`` kwarg).
        horizon_start = now
    else:
        wall_clock = datetime.now()
        default_end = wall_clock + timedelta(hours=WINDOW_HOURS * horizon_days)
        future_etas = [eta for eta, _ in arrivals if eta >= wall_clock]
        if future_etas and min(future_etas) >= default_end:
            # All future vessels arrive after the current 72-hour window ends.
            # Anchor the horizon to the earliest ETA so the forecast is useful.
            horizon_start = min(future_etas)
            logger.info(
                "All vessel ETAs are beyond the current 72h window; "
                "anchoring forecast to earliest ETA %s.",
                horizon_start.strftime(ETA_FORMAT),
            )
        elif future_etas:
            horizon_start = wall_clock
        else:
            # All vessel ETAs in the dataset lie in the past relative to wall clock.
            # Anchor the horizon to the earliest arrival in the dataset so a past-dated
            # dataset (e.g. bundled sample CSVs) produces a complete, useful forecast.
            horizon_start = min(eta for eta, _ in arrivals)
            logger.info(
                "All vessel ETAs are in the past relative to system time; "
                "anchoring forecast to earliest ETA %s.",
                horizon_start.strftime(ETA_FORMAT),
            )

    horizon_end = horizon_start + timedelta(hours=WINDOW_HOURS * horizon_days)

    windows: dict[int, list[int]] = defaultdict(list)
    beyond_horizon = 0
    past_horizon = 0
    for eta, size in arrivals:
        if eta < horizon_start:
            past_horizon += 1
            continue
        if eta >= horizon_end:
            beyond_horizon += 1
            continue
        window_index = int((eta - horizon_start).total_seconds() // (WINDOW_HOURS * 3600))
        windows[window_index].append(size)

    if beyond_horizon or past_horizon:
        logger.info(
            "%d vessel(s) arrive outside the %dh horizon (past: %d, future: %d) "
            "and are excluded from the forecast.",
            past_horizon + beyond_horizon,
            WINDOW_HOURS * horizon_days,
            past_horizon,
            beyond_horizon,
        )

    results: list[dict[str, object]] = []
    for window_index in range(horizon_days):
        sizes = windows.get(window_index, [])
        incoming_teu = sum(sizes)
        risk_ratio = incoming_teu / total_capacity
        if risk_ratio > high:
            rule_risk_level = "HIGH"
        elif risk_ratio > medium:
            rule_risk_level = "MEDIUM"
        else:
            rule_risk_level = "LOW"
        risk_level = rule_risk_level  # ML may override below

        if settings.ml_enabled and using_default_thresholds:
            try:
                from portpulse.ml.predictor import log_prediction, predict_risk

                ml_risk = predict_risk(
                    {
                        "vessel_count": len(sizes),
                        "incoming_teu": incoming_teu,
                        "total_capacity_teu": total_capacity,
                        "day_index": window_index + 1,
                        "utilization_ratio": round(risk_ratio, 2),
                    }
                )
                if ml_risk is not None:
                    risk_level = ml_risk

                log_prediction(
                    vessel_id=f"WINDOW_DAY_{window_index + 1}",
                    window_day=window_index + 1,
                    vessel_count=len(sizes),
                    incoming_teu=incoming_teu,
                    total_capacity_teu=total_capacity,
                    utilization_ratio=round(risk_ratio, 2),
                    predicted_risk_level=risk_level,
                    predicted_wait_hours=None,
                )
            except Exception as err:
                logger.warning("ML window risk prediction or logging failed: %s", err)

        window_start = horizon_start + timedelta(hours=WINDOW_HOURS * window_index)
        window_end = window_start + timedelta(hours=WINDOW_HOURS)

        if sizes:
            reason = (
                f"{len(sizes)} vessels ({incoming_teu:,} TEU) arriving vs "
                f"{total_capacity:,} TEU total berth capacity"
            )
        else:
            reason = f"No incoming vessels scheduled in Day {window_index + 1} 24-hour window."

        results.append(
            {
                "day": window_index + 1,
                "window_start": window_start.strftime(ETA_FORMAT),
                "window_end": window_end.strftime(ETA_FORMAT),
                "vessel_count": len(sizes),
                "incoming_teu": incoming_teu,
                "total_capacity_teu": total_capacity,
                "risk_ratio": round(risk_ratio, 2),
                "risk_level": risk_level,
                "rule_risk_level": rule_risk_level,
                "reason": reason,
            }
        )

    return results
