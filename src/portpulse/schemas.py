"""Request and response models.

Input models enforce the data contract at the edge (types, ranges, timestamp
format) so the domain layer can assume well-formed values. Response models give
the OpenAPI schema a real output contract instead of bare dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from portpulse.constants import ETA_FORMAT

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

Teu = Annotated[int, Field(gt=0, le=100_000, description="Twenty-foot equivalent units")]
Priority = Annotated[int, Field(ge=1, le=5, description="1 = highest priority")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ── Inputs ───────────────────────────────────────────────────────────────────


class VesselIn(_Model):
    """A single incoming vessel."""

    vessel_id: str = Field(min_length=1, max_length=64, examples=["V001"])
    name: str = Field(min_length=1, max_length=128, examples=["MV Horizon-1"])
    eta: str = Field(examples=["2026-10-01 08:00"], description=f"Timestamp as {ETA_FORMAT}")
    size_teu: Teu = Field(examples=[9000])
    cargo_type: str = Field(min_length=1, max_length=64, examples=["reefer"])
    priority: Priority = Field(examples=[1])

    @field_validator("eta")
    @classmethod
    def _validate_eta(cls, value: str) -> str:
        try:
            datetime.strptime(value, ETA_FORMAT)
        except ValueError as err:
            raise ValueError(f"eta must match '{ETA_FORMAT}' (e.g. 2026-10-01 08:00)") from err
        return value

    def to_row(self) -> dict[str, str]:
        """Render as a CSV-shaped row so the domain layer sees one uniform format."""
        return {key: str(value) for key, value in self.model_dump().items()}


class BerthIn(_Model):
    """A single berth and its handling capacity."""

    berth_id: str = Field(min_length=1, max_length=64, examples=["B1"])
    capacity_teu: Teu = Field(examples=[16000])
    crane_count: int = Field(ge=0, le=50, examples=[4])
    avg_dwell_hours: float = Field(gt=0, le=720, examples=[24.0])

    def to_row(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.model_dump().items()}


class CustomPlanRequest(_Model):
    """Generate a plan from data supplied in the request body."""

    vessels: list[VesselIn] = Field(min_length=1, max_length=5_000)
    berths: list[BerthIn] = Field(min_length=1, max_length=500)


class ScenarioSpec(_Model):
    """Scenario modification specification."""

    type: Literal["delay_vessel", "berth_outage"] = Field(examples=["delay_vessel"])
    vessel_id: str | None = Field(default=None, examples=["V001"])
    delay_hours: float | None = Field(default=None, gt=0, examples=[6.0])
    berth_id: str | None = Field(default=None, examples=["B1"])
    hours: float | None = Field(default=None, gt=0, examples=[24.0])

    @model_validator(mode="after")
    def _validate_scenario_fields(self) -> ScenarioSpec:
        if self.type == "delay_vessel" and (
            not self.vessel_id or self.delay_hours is None or self.delay_hours <= 0
        ):
            raise ValueError(
                "vessel_id and positive delay_hours (> 0) are required when type='delay_vessel'"
            )
        if self.type == "berth_outage" and (
            not self.berth_id or self.hours is None or self.hours <= 0
        ):
            raise ValueError(
                "berth_id and positive hours (> 0) are required when type='berth_outage'"
            )
        return self


class WhatIfRequest(_Model):
    """Input payload for What-If simulation."""

    vessels: list[VesselIn] | None = Field(default=None)
    berths: list[BerthIn] | None = Field(default=None)
    scenario: ScenarioSpec

    @model_validator(mode="after")
    def _validate_datasets(self) -> WhatIfRequest:
        if (self.vessels is None) != (self.berths is None):
            raise ValueError("vessels and berths must both be provided or both be omitted")
        return self


class CascadeRequest(_Model):
    """Input payload for Cascading Impact simulation."""

    vessels: list[VesselIn] | None = Field(default=None)
    berths: list[BerthIn] | None = Field(default=None)
    disruption: ScenarioSpec
    max_iterations: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def _validate_datasets(self) -> CascadeRequest:
        if (self.vessels is None) != (self.berths is None):
            raise ValueError("vessels and berths must both be provided or both be omitted")
        return self


# ── Outputs ──────────────────────────────────────────────────────────────────


class CongestionWindow(BaseModel):
    """Risk assessment for one 24-hour window."""

    day: int = Field(ge=1, examples=[1])
    window_start: str
    window_end: str
    vessel_count: int = Field(ge=0)
    incoming_teu: int = Field(ge=0)
    total_capacity_teu: int = Field(ge=0)
    risk_ratio: float = Field(ge=0)
    risk_level: RiskLevel
    reason: str


class BerthAssignment(BaseModel):
    """One vessel placed at one berth."""

    vessel_id: str
    vessel_name: str
    berth_id: str
    crane_count: int | None = None
    effective_dwell_hours: float | None = Field(
        default=None, description="Effective dwell time in hours after crane scaling"
    )
    arrival: str
    berth_start: str
    departure_est: str
    wait_hours: float = Field(ge=0)
    priority: int | None = None
    size_teu: int | None = Field(default=None, description="Vessel capacity volume in TEU")
    reason: str


class AlternatePort(BaseModel):
    """A candidate port for a vessel that could not be berthed."""

    port: str
    distance_km: int = Field(ge=0)
    spare_capacity_teu: int = Field(ge=0)
    reason: str


class RerouteSuggestion(BaseModel):
    """Routing recommendation for one unassigned vessel."""

    vessel_id: str
    vessel_name: str
    reason_unassigned: str
    ai_generated: bool = Field(
        default=False,
        description="True when the reasoning text came from watsonx.ai rather than a template.",
    )
    alternatives: list[AlternatePort] = Field(default_factory=list)


class KpiSummary(BaseModel):
    """High-level operations performance metrics calculated from the plan."""

    avg_wait_hours: float = Field(
        ge=0, description="Average queue wait hours across assigned vessels"
    )
    berth_utilization_pct: float = Field(
        ge=0, description="Total assigned TEU volume vs berth capacity percentage"
    )
    vessels_at_risk: int = Field(ge=0, description="Count of unassigned / rerouted vessels")
    estimated_emissions_saved_kg: float = Field(
        ge=0,
        description="Illustrative estimate of CO2 emissions saved (kg) (estimate, not quoted rate)",
    )


class SwapOpportunity(BaseModel):
    """Advisory recommendation to swap two berthed vessels."""

    vessel_1_id: str
    vessel_1_name: str
    vessel_2_id: str
    vessel_2_name: str
    hours_saved: float = Field(gt=0)
    estimated_cost_saved: float = Field(
        ge=0, description="Cost savings using DEMURRAGE_RATE_PER_TEU_HOUR"
    )
    reason: str


class OpsPlan(BaseModel):
    """The complete 72-hour operations plan returned to the dashboard."""

    generated_at: str
    freshness_status: Literal["FRESH", "STALE"] = "FRESH"
    data_age_seconds: int = Field(default=0, ge=0)
    source_name: str = "TOS"
    kpis: KpiSummary | None = None
    congestion_forecast: list[CongestionWindow] = Field(default_factory=list)
    berth_assignments: list[BerthAssignment] = Field(default_factory=list)
    unassigned_count: int = Field(default=0, ge=0)
    reroute_suggestions: list[RerouteSuggestion] = Field(default_factory=list)
    swap_opportunities: list[SwapOpportunity] = Field(default_factory=list)
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal degradations, e.g. a sub-engine that failed.",
    )


class HealthResponse(BaseModel):
    """Liveness / readiness payload."""

    status: Literal["healthy", "degraded"]
    service: str
    version: str
    environment: str
    watsonx_configured: bool
    datasets_available: bool


class ErrorResponse(BaseModel):
    """Uniform error envelope used by every failure path."""

    detail: str
