"""Tests for Pydantic request and response schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from portpulse.schemas import BerthIn, CascadeRequest, ScenarioSpec, VesselIn, WhatIfRequest


def test_scenario_spec_valid_delay_vessel() -> None:
    spec = ScenarioSpec(type="delay_vessel", vessel_id="V001", delay_hours=5.0)
    assert spec.type == "delay_vessel"
    assert spec.vessel_id == "V001"


def test_scenario_spec_invalid_delay_vessel_missing_fields() -> None:
    with pytest.raises(ValidationError, match="vessel_id and delay_hours are required"):
        ScenarioSpec(type="delay_vessel", delay_hours=5.0)

    with pytest.raises(ValidationError, match="vessel_id and delay_hours are required"):
        ScenarioSpec(type="delay_vessel", vessel_id="V001")


def test_scenario_spec_valid_berth_outage() -> None:
    spec = ScenarioSpec(type="berth_outage", berth_id="B1", hours=12.0)
    assert spec.type == "berth_outage"
    assert spec.berth_id == "B1"


def test_scenario_spec_invalid_berth_outage_missing_fields() -> None:
    with pytest.raises(ValidationError, match="berth_id and hours are required"):
        ScenarioSpec(type="berth_outage", hours=12.0)

    with pytest.raises(ValidationError, match="berth_id and hours are required"):
        ScenarioSpec(type="berth_outage", berth_id="B1")


def test_whatif_request_datasets_validation() -> None:
    spec = ScenarioSpec(type="berth_outage", berth_id="B1", hours=12.0)
    vessel = VesselIn(
        vessel_id="V001",
        name="MV Alpha",
        eta="2026-10-01 08:00",
        size_teu=5000,
        cargo_type="reefer",
        priority=1,
    )
    berth = BerthIn(berth_id="B1", capacity_teu=16000, crane_count=4, avg_dwell_hours=6.0)

    # Valid: both None
    req1 = WhatIfRequest(scenario=spec)
    assert req1.vessels is None and req1.berths is None

    # Valid: both provided
    req2 = WhatIfRequest(scenario=spec, vessels=[vessel], berths=[berth])
    assert req2.vessels is not None and req2.berths is not None

    # Invalid: only vessels provided
    with pytest.raises(ValidationError, match="vessels and berths must both be provided"):
        WhatIfRequest(scenario=spec, vessels=[vessel])

    # Invalid: only berths provided
    with pytest.raises(ValidationError, match="vessels and berths must both be provided"):
        WhatIfRequest(scenario=spec, berths=[berth])


def test_cascade_request_datasets_validation() -> None:
    spec = ScenarioSpec(type="berth_outage", berth_id="B1", hours=12.0)
    vessel = VesselIn(
        vessel_id="V001",
        name="MV Alpha",
        eta="2026-10-01 08:00",
        size_teu=5000,
        cargo_type="reefer",
        priority=1,
    )

    # Invalid: only vessels provided
    with pytest.raises(ValidationError, match="vessels and berths must both be provided"):
        CascadeRequest(disruption=spec, vessels=[vessel])
