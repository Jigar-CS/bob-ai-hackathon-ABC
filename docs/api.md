# PortPulse — API Reference Specification

Base URL in local development: `http://127.0.0.1:8000`.
An always-current, interactive OpenAPI documentation UI is served at `/api/docs`.

Business endpoints are versioned under `/api/v1`. `/health` is unversioned for stable orchestrator health probes.

---

## Authentication

Read endpoints are public. Write endpoints require an `X-API-Key` header **when** `PORTPULSE_API_KEY` is configured:

| Endpoint | Requires API Key |
|---|---|
| `POST /api/v1/plan/custom` | ✓ |
| `POST /api/v1/uploads/{dataset}` | ✓ |
| `POST /api/v1/chat` | ✓ |
| `POST /api/v1/plan/whatif` | — |
| `POST /api/v1/cascade-simulation` | — |
| All `GET` endpoints | — |
| `POST /api/v1/summary` | — |

---

## Rate Limiting

`POST` requests to sensitive endpoints (`/api/v1/chat`, `/api/v1/uploads/*`, `/api/v1/plan/custom`) are subject to a sliding-window rate limit of **30 requests per minute per IP**. Excess requests receive `429 Too Many Requests` with a `Retry-After: 60` header.

---

## Error Envelope

Every failure returns a standardized error contract:

```json
{ "detail": "CSV missing required columns: cargo_type, eta" }
```

| Status | Meaning |
|---|---|
| `400` | Malformed input: bad encoding, missing CSV columns, or invalid simulation guard spec. |
| `401` | Missing or incorrect `X-API-Key`. |
| `413` | Upload exceeds `PORTPULSE_MAX_UPLOAD_BYTES`. |
| `422` | Request payload failed Pydantic validation. |
| `429` | Rate limit exceeded. |
| `500` | Unexpected error. Response carries reference ID matching `X-Request-ID` in server logs. |
| `503` | Default datasets missing or unreadable. |

---

## Endpoint Specifications

### `GET /health`
Liveness and readiness check. Returns `200` when datasets are readable and `503` when missing.

```json
{
  "status": "healthy",
  "service": "portpulse",
  "version": "1.0.0",
  "environment": "development",
  "watsonx_configured": true,
  "datasets_available": true
}
```

---

### `GET /api/v1/plan`
Generates the complete 72-hour operations plan, high-level KPIs, and Top 5 berth swap recommendations.

```json
{
  "generated_at": "2026-09-15T08:00:00+00:00",
  "freshness_status": "FRESH",
  "data_age_seconds": 0,
  "source_name": "TOS",
  "kpis": {
    "avg_wait_hours": 2.15,
    "berth_utilization_pct": 42.8,
    "vessels_at_risk": 25,
    "estimated_emissions_saved_kg": 48002.5
  },
  "swap_opportunities": [
    {
      "vessel_1_id": "V001",
      "vessel_1_name": "MV Horizon-1",
      "vessel_2_id": "V004",
      "vessel_2_name": "MV Horizon-4",
      "hours_saved": 4.5,
      "estimated_cost_saved": 1912.5,
      "reason": "Swapping MV Horizon-1 (P1) with MV Horizon-4 (P2) prioritizes time-critical cargo and reduces P1 queue wait by 4.5h."
    }
  ],
  "congestion_forecast": [
    {
      "day": 1,
      "window_start": "2026-09-15 08:00",
      "window_end": "2026-09-16 08:00",
      "vessel_count": 14,
      "incoming_teu": 104000,
      "total_capacity_teu": 74000,
      "risk_ratio": 1.41,
      "risk_level": "HIGH",
      "reason": "14 vessels (104,000 TEU) arriving vs 74,000 TEU total berth capacity"
    }
  ],
  "berth_assignments": [
    {
      "vessel_id": "V004",
      "vessel_name": "MV Horizon-4",
      "berth_id": "B3",
      "crane_count": 4,
      "arrival": "2026-09-15 07:30",
      "berth_start": "2026-09-15 07:30",
      "departure_est": "2026-09-16 07:06",
      "wait_hours": 0.0,
      "priority": 1,
      "size_teu": 8500,
      "reason": "P1, fits B3 capacity, berth free on arrival"
    }
  ],
  "unassigned_count": 1,
  "reroute_suggestions": [ ... ],
  "warnings": []
}
```

---

### `POST /api/v1/plan/whatif`
Sandboxed What-If scenario simulator comparing baseline vs modified scenario.

#### Request Body
```json
{
  "scenario": {
    "type": "delay_vessel",
    "vessel_id": "V001",
    "delay_hours": 6.0
  }
}
```

#### Response Body
```json
{
  "scenario": { "type": "delay_vessel", "vessel_id": "V001", "delay_hours": 6.0 },
  "diff_summary": {
    "reassigned_count": 2,
    "newly_unassigned_count": 0,
    "reassigned_vessels": [
      {
        "vessel_id": "V002",
        "vessel_name": "MV Horizon-2",
        "baseline_berth": "B1",
        "modified_berth": "B2",
        "baseline_start": "2026-09-15 10:00",
        "modified_start": "2026-09-15 12:00"
      }
    ],
    "newly_unassigned_vessels": [],
    "risk_level_changes": []
  }
}
```

---

### `POST /api/v1/cascade-simulation`
Iterative multi-pass schedule ripple simulation analyzing downstream queue delays and financial demurrage cost impact.

#### Request Body
```json
{
  "disruption": {
    "type": "berth_outage",
    "berth_id": "B1",
    "hours": 24.0
  },
  "max_iterations": 5
}
```

#### Response Body
```json
{
  "iterations_run": 2,
  "stabilized": true,
  "total_vessels_affected": 8,
  "total_cascade_delay_hours": 75.35,
  "total_estimated_cost": 23622.0,
  "affected_vessels": [
    {
      "vessel_id": "V005",
      "vessel_name": "MV Horizon-5",
      "delay_hours": 2.0,
      "cascade_depth": 1,
      "reason": "Berth start delayed by 2.0h (Pass #1)",
      "size_teu": 6500,
      "cost_impact": 650.0
    }
  ]
}
```

---

### `POST /api/v1/chat`
Answers supervisor operational questions grounded in live 72-hour plan data. Enforces pre-LLM domain scope gating.

#### Request Body
```json
{
  "message": "Which vessel is assigned to B3, and when does it depart?",
  "plan": { ... },
  "history": [
    { "role": "user", "content": "What is the congestion level today?" },
    { "role": "assistant", "content": "Day 1 is at HIGH risk..." }
  ]
}
```

#### Response Body
```json
{
  "reply": "MV Horizon-4 is berthed at **Berth B3**. It arrived at 2026-09-15 07:30 and is estimated to depart at 2026-09-16 07:06.",
  "ai_generated": true
}
```
