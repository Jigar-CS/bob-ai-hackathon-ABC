"""Plan orchestration — combines forecasting, assignment and routing.

Each stage is isolated: if one engine fails, the plan is still returned with the
remaining sections populated and a human-readable entry in ``warnings``. A shift
supervisor gets partial information rather than an error page.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from portpulse.csv_io import Row
from portpulse.domain.assignment import AssignmentResult, assign_berths
from portpulse.domain.prediction import predict_congestion
from portpulse.domain.routing import suggest_alternates
from portpulse.errors import PlanningError

logger = logging.getLogger(__name__)


def generate_ops_plan(
    vessels: list[Row],
    berths: list[Row],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the complete 72-hour operations plan.

    Args:
        vessels: Vessel schedule rows.
        berths: Berth capacity rows.
        now: Reference start time for the congestion horizon; defaults to the
            current system time. Pass explicitly in tests to get deterministic
            window boundaries.

    Returns:
        A dict matching :class:`portpulse.schemas.OpsPlan`.
    """
    warnings: list[str] = []

    try:
        congestion = predict_congestion(vessels, berths, now=now)
    except PlanningError as err:
        logger.warning("Congestion forecast unavailable: %s", err)
        congestion = []
        warnings.append(f"Congestion forecast unavailable: {err}")
    except Exception:
        logger.exception("Congestion forecast failed unexpectedly.")
        congestion = []
        warnings.append("Congestion forecast unavailable due to an internal error.")

    try:
        assignment = assign_berths(vessels, berths)
    except PlanningError as err:
        logger.warning("Berth assignment unavailable: %s", err)
        assignment = AssignmentResult(assigned=[], unassigned=list(vessels))
        warnings.append(f"Berth assignment unavailable: {err}")
    except Exception:
        logger.exception("Berth assignment failed unexpectedly.")
        assignment = AssignmentResult(assigned=[], unassigned=list(vessels))
        warnings.append("Berth assignment unavailable due to an internal error.")

    try:
        reroutes = suggest_alternates(assignment.unassigned)
    except Exception:
        logger.exception("Routing suggestions failed unexpectedly.")
        reroutes = []
        warnings.append("Alternate routing suggestions unavailable due to an internal error.")

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "congestion_forecast": congestion,
        "berth_assignments": assignment.assigned,
        "unassigned_count": len(assignment.unassigned),
        "reroute_suggestions": reroutes,
        "warnings": warnings,
    }
