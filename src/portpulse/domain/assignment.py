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
from portpulse.csv_io import Row
from portpulse.errors import PlanningError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Berth:
    berth_id: str
    capacity_teu: int
    avg_dwell_hours: float
    crane_count: int | None
    free_at: datetime


@dataclass(slots=True)
class _Vessel:
    row: Row
    vessel_id: str
    name: str
    eta: datetime
    size_teu: int
    priority: int | None


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
            eta = datetime.strptime(str(vessel["eta"]), ETA_FORMAT)
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

        parsed.append(
            _Vessel(
                row=vessel,
                vessel_id=str(vessel.get("vessel_id") or "UNKNOWN"),
                name=str(vessel.get("name") or "Unknown Vessel"),
                eta=eta,
                size_teu=size_teu,
                priority=raw_priority,
            )
        )
    return parsed, rejected


def assign_berths(
    vessels: list[Row],
    berths: list[Row],
    *,
    max_wait_hours: float | None = None,
) -> AssignmentResult:
    """Allocate vessels to berths.

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
    limit = get_settings().app.max_berth_wait_hours if max_wait_hours is None else max_wait_hours

    if not berths:
        raise PlanningError("At least one berth is required to assign vessels.")

    available = _parse_berths(berths)
    if not available:
        raise PlanningError("No berth rows were usable — check the berth dataset.")

    if not vessels:
        return AssignmentResult(assigned=[], unassigned=[])

    parsed_vessels, unassigned = _parse_vessels(vessels)
    # Priority ascending (1 first), unknown priority last, then earliest arrival.
    parsed_vessels.sort(key=lambda v: (v.priority if v.priority is not None else 99, v.eta))

    assigned: list[dict[str, object]] = []

    for vessel in parsed_vessels:
        best: _Berth | None = None
        best_start: datetime | None = None
        best_wait = 0.0

        for berth in available:
            if vessel.size_teu > berth.capacity_teu:
                continue
            start_time = max(vessel.eta, berth.free_at)
            wait_hours = (start_time - vessel.eta).total_seconds() / 3600.0
            if wait_hours > limit:
                continue
            if best_start is None or start_time < best_start:
                best, best_start, best_wait = berth, start_time, wait_hours

        if best is None or best_start is None:
            unassigned.append(vessel.row)
            continue

        departure = best_start + timedelta(hours=best.avg_dwell_hours)
        best.free_at = departure

        priority_label = f"P{vessel.priority}" if vessel.priority is not None else "unprioritised"
        if best_wait == 0:
            reason = f"{priority_label}, fits {best.berth_id} capacity, berth free on arrival"
        else:
            reason = f"{priority_label}, queued {best_wait:.1f}h for berth {best.berth_id}"

        assigned.append(
            {
                "vessel_id": vessel.vessel_id,
                "vessel_name": vessel.name,
                "berth_id": best.berth_id,
                "crane_count": best.crane_count,
                "arrival": vessel.eta.strftime(ETA_FORMAT),
                "berth_start": best_start.strftime(ETA_FORMAT),
                "departure_est": departure.strftime(ETA_FORMAT),
                "wait_hours": round(best_wait, 1),
                "priority": vessel.priority,
                "size_teu": vessel.size_teu,
                "reason": reason,
            }
        )

    return AssignmentResult(assigned=assigned, unassigned=unassigned)
