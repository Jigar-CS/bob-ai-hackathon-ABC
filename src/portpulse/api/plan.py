"""Operations-plan endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from portpulse.config import Settings, get_settings
from portpulse.csv_io import Row, table_to_csv
from portpulse.datasets import load_berths, load_vessels
from portpulse.domain.chat import answer as chat_answer
from portpulse.domain.planner import generate_ops_plan
from portpulse.domain.summary import generate_ops_summary
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


@router.get(
    "/summary",
    summary="Get a plain-language operations summary for the shift supervisor",
    responses=_DATA_ERROR_RESPONSES,
)
def get_summary() -> dict[str, object]:
    """Generate a 3-4 sentence plain-language summary of the current ops plan.

    Uses watsonx.ai when configured; falls back to a templated summary otherwise.
    Never returns a 500 — the caller always receives a ``summary`` string.
    """
    plan = generate_ops_plan(load_vessels(), load_berths())
    return generate_ops_summary(plan)


@router.post(
    "/summary",
    summary="Get a plain-language summary for a plan supplied in the request body",
)
def post_summary(payload: OpsPlan) -> dict[str, object]:
    """Generate a summary from a plan already computed by the client.

    Used by the dashboard after a custom CSV upload so the summary reflects the
    uploaded data rather than the default datasets.  Never returns a 500.
    """
    plan = payload.model_dump()
    return generate_ops_summary(plan)


# ── Chat ──────────────────────────────────────────────────────────────────────


class _ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=5000)


class _ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    plan: OpsPlan
    history: list[_ChatTurn] = Field(default_factory=list, max_length=20)


@router.post(
    "/chat",
    summary="Ask a plain-English question about the live ops plan",
    dependencies=[Depends(require_api_key)],
)
def post_chat(payload: _ChatRequest) -> dict[str, Any]:
    """Answer one supervisor question grounded in the supplied ops plan.

    Uses watsonx.ai (ibm/granite-3-8b-instruct) when configured; falls back to
    structured rule-based replies otherwise.  Never returns a 500.
    """
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    return chat_answer(
        user_message=payload.message,
        plan=payload.plan.model_dump(),
        history=history,
    )
