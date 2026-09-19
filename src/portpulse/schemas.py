"""Request and response models.

Input models enforce the data contract at the edge (types, ranges, timestamp
format) so the domain layer can assume well-formed values. Response models give
the OpenAPI schema a real output contract instead of bare dicts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Annotated, Literal

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
    origin_lat: float | None = Field(default=None, ge=-90.0, le=90.0, examples=[25.2048])
    origin_lon: float | None = Field(default=None, ge=-180.0, le=180.0, examples=[55.2708])
    origin_port: str | None = Field(default=None, max_length=128, examples=["Dubai"])
    dest_lat: float | None = Field(default=None, ge=-90.0, le=90.0, examples=[33.73])
    dest_lon: float | None = Field(default=None, ge=-180.0, le=180.0, examples=[-118.26])
    dest_port: str | None = Field(default=None, max_length=128, examples=["LA/Long Beach"])

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
        return {key: str(value) for key, value in self.model_dump().items() if value is not None}


class BerthIn(_Model):
    """A single berth and its handling capacity."""

    berth_id: str = Field(min_length=1, max_length=64, examples=["B1"])
    capacity_teu: Teu = Field(examples=[16000])
    crane_count: int = Field(ge=0, le=50, examples=[4])
    avg_dwell_hours: float = Field(gt=0, le=720, examples=[24.0])
    allowed_cargo_types: str | None = Field(
        default=None, examples=["container, bulk, limestone"]
    )

    def to_row(self) -> dict[str, str]:
        return {key: str(value) for key, value in self.model_dump().items() if value is not None}


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
    rule_risk_level: RiskLevel = Field(
        default="LOW",
        description="Rule-based risk level before any ML override",
    )
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
    predicted_wait_hours: float | None = Field(
        default=None, description="ML-predicted wait time in hours"
    )
    predicted_demurrage_cost_usd: float | None = Field(
        default=None, description="ML-predicted demurrage cost impact in USD"
    )
    predicted_moves_per_hour: float | None = Field(
        default=None, description="ML-predicted crane handling speed in moves/hour"
    )
    is_anomalous: bool | None = Field(
        default=None, description="True if vessel dwell/wait pattern is flagged as an anomaly"
    )
    weather_delay_hours: float | None = Field(
        default=None,
        description="Hours added to ETA due to adverse weather along the vessel's route",
    )
    weather_severity: str | None = Field(
        default=None,
        description="Weather severity tier: none / minor / moderate / severe",
    )
    queue_position: int | None = Field(
        default=None, description="0-indexed position in berth waiting queue"
    )
    queue_status: str | None = Field(
        default=None, description="Queue status: BERTHED or QUEUED (#N)"
    )
    queued_behind: str | None = Field(
        default=None, description="Name of vessel immediately preceding in berth queue"
    )
    origin_port: str | None = Field(default=None, description="Departure origin port")
    dest_port: str | None = Field(default=None, description="Destination port")


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
        ge=0,
        description="Average wait hours — ML predicted when available, else rule-based",
    )
    berth_utilization_pct: float = Field(
        ge=0, description="Total assigned TEU volume vs berth capacity percentage"
    )
    vessels_at_risk: int = Field(ge=0, description="Count of unassigned / rerouted vessels")
    estimated_emissions_saved_kg: float = Field(
        ge=0,
        description="Illustrative estimate of CO2 emissions saved (kg) (estimate, not quoted rate)",
    )
    total_predicted_demurrage_usd: float = Field(
        default=0.0,
        ge=0,
        description="Sum of ML-predicted demurrage costs across all assigned vessels (USD)",
    )
    weather_delayed_vessels: int = Field(
        default=0,
        ge=0,
        description="Count of vessels whose ETA was adjusted due to adverse weather",
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


class WeatherDelayInfo(BaseModel):
    """Per-vessel weather delay summary entry."""

    vessel_id: str
    vessel_name: str
    origin_lat: float | None = None
    origin_lon: float | None = None
    delay_hours: float = Field(ge=0)
    severity: str = Field(
        default="none",
        description="Weather severity tier: none / minor / moderate / severe",
    )


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
    weather_summary: list[WeatherDelayInfo] = Field(
        default_factory=list,
        description="Weather-induced ETA delays applied before berth assignment.",
    )
    ml_enabled: bool = Field(description="True when ML model features and predictions are enabled.")
    ml_allocation_used: bool = Field(description="True when ML model berth allocation was used for assignments.")
    meta: dict[str, Any] | None = Field(
        default=None,
        description="Home port metadata including home_port_name, home_port_lat, and home_port_lon.",
    )
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
