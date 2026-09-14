"""Operations-plan endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response, status

from portpulse.config import Settings, get_settings
from portpulse.csv_io import Row, table_to_csv
from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.planner import generate_ops_plan
from portpulse.schemas import CustomPlanRequest, ErrorResponse, OpsPlan
from portpulse.security import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plan"])

EXPORT_COLUMNS = (
    "vessel_id",
    "vessel_name",
    "status",
    "berth_id",
    "crane_count",
    "arrival",
    "berth_start",
    "departure_est",
    "wait_hours",
    "priority",
    "notes",
)

_DATA_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Default datasets are missing or unreadable.",
    }
}


@router.get(
    "/plan",
    response_model=OpsPlan,
    summary="Generate the 72-hour plan from the default datasets",
    responses=_DATA_ERROR_RESPONSES,
)
def get_plan() -> OpsPlan:
    """Build a plan from the bundled vessel and berth datasets."""
    plan = generate_ops_plan(load_vessels(), load_berths())
    return OpsPlan.model_validate(plan)


@router.post(
    "/plan/custom",
    response_model=OpsPlan,
    summary="Generate a plan from vessel and berth data in the request body",
    dependencies=[Depends(require_api_key)],
)
def post_custom_plan(payload: CustomPlanRequest) -> OpsPlan:
    """Build a plan from fully validated JSON input."""
    vessels: list[Row] = [vessel.to_row() for vessel in payload.vessels]
    berths: list[Row] = [berth.to_row() for berth in payload.berths]
    logger.info(
        "Generating plan from request body (%d vessels, %d berths)", len(vessels), len(berths)
    )
    return OpsPlan.model_validate(generate_ops_plan(vessels, berths))


@router.get(
    "/plan/export.csv",
    response_class=Response,
    summary="Export the plan as a flat CSV for spreadsheets and TOS imports",
    responses={
        200: {"content": {"text/csv": {}}, "description": "Flat CSV of the current plan."},
        **_DATA_ERROR_RESPONSES,
    },
)
def export_plan_csv(settings: Settings = Depends(get_settings)) -> Response:
    """Flatten the plan into one row per vessel, berthed or rerouted."""
    plan = generate_ops_plan(load_vessels(settings), load_berths(settings))

    records: list[list[object]] = [
        [
            assignment["vessel_id"],
            assignment["vessel_name"],
            "BERTHED",
            assignment["berth_id"],
            assignment["crane_count"] if assignment["crane_count"] is not None else "",
            assignment["arrival"],
            assignment["berth_start"],
            assignment["departure_est"],
            assignment["wait_hours"],
            assignment["priority"] if assignment["priority"] is not None else "",
            assignment["reason"],
        ]
        for assignment in plan["berth_assignments"]
    ]

    for reroute in plan["reroute_suggestions"]:
        alternatives = "; ".join(
            f"{alt['port']} ({alt['distance_km']}km)" for alt in reroute["alternatives"]
        )
        records.append(
            [
                reroute["vessel_id"],
                reroute["vessel_name"],
                "REROUTED",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                f"{reroute['reason_unassigned']} | Alternatives: {alternatives}",
            ]
        )

    return Response(
        content=table_to_csv(EXPORT_COLUMNS, records),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="portpulse_ops_plan.csv"'},
    )
