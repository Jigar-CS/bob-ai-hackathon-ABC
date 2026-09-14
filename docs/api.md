# API Reference

Base URL in local development: `http://127.0.0.1:8000`.
An always-current, interactive version is served at `/api/docs`, generated from
the same Pydantic models the endpoints use.

Business endpoints are versioned under `/api/v1`. `/health` is deliberately
unversioned so orchestrators have a stable probe URL.

## Authentication

Read endpoints are public. Write endpoints — `POST /api/v1/plan/custom` and
`POST /api/v1/uploads/{dataset}` — require an `X-API-Key` header **when**
`PORTPULSE_API_KEY` is configured. If it is unset, they are open, which is
intended for local use only; the application refuses to start in production
without a key.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/plan/custom \
  -H "X-API-Key: $PORTPULSE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @plan-request.json
```

## Errors

Every failure returns the same envelope:

```json
{ "detail": "CSV missing required columns: cargo_type, eta" }
```

| Status | Meaning |
|---|---|
| `400` | Malformed CSV: bad encoding, missing columns, no data rows, wrong extension. |
| `401` | Missing or incorrect `X-API-Key`. |
| `413` | Upload exceeds `PORTPULSE_MAX_UPLOAD_BYTES`. |
| `422` | Request body failed validation, or a plan is impossible from the input. |
| `500` | Unexpected error. The response carries a reference matching the `X-Request-ID` in the logs. |
| `503` | Default datasets are missing or unreadable. |

Every response includes an `X-Request-ID` header. Supply your own to trace a call
across a proxy; otherwise one is generated.

---

## `GET /health`

Liveness and readiness. Returns `200` when the datasets are readable and `503`
when they are not. Missing watsonx.ai credentials do **not** make the service
unhealthy, because routing degrades gracefully.

```json
{
  "status": "healthy",
  "service": "portpulse",
  "version": "1.0.0",
  "environment": "development",
  "watsonx_configured": false,
  "datasets_available": true
}
```

---

## `GET /api/v1/plan`

The full 72-hour operations plan built from the configured datasets.

```json
{
  "generated_at": "2026-09-13T09:15:00+00:00",
  "congestion_forecast": [
    {
      "day": 1,
      "window_start": "2026-09-15 06:12",
      "window_end": "2026-09-16 06:12",
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
      "reason": "P1, fits B3 capacity, berth free on arrival"
    }
  ],
  "unassigned_count": 1,
  "reroute_suggestions": [
    {
      "vessel_id": "V021",
      "vessel_name": "MV Horizon-21",
      "reason_unassigned": "No berth had capacity or availability within the 72-hour window",
      "ai_generated": false,
      "alternatives": [
        {
          "port": "Port of Ensenada",
          "distance_km": 240,
          "spare_capacity_teu": 4000,
          "reason": "4,000 TEU spare capacity, 240km away"
        }
      ]
    }
  ],
  "warnings": []
}
```

Field notes:

- `risk_ratio` is arriving TEU divided by total berth capacity, so values above
  `1.0` are expected and meaningful.
- `ai_generated` is `true` only when watsonx.ai text was successfully used. When
  it is `false`, the text is the deterministic template.
- `warnings` lists engines that degraded. An empty list means every stage
  completed. A populated list still accompanies a usable plan.

---

## `POST /api/v1/plan/custom`

Plan from data in the request body. Fully validated: unknown fields are
rejected, `size_teu` must be positive, `priority` must be 1–5, and `eta` must
match `YYYY-MM-DD HH:MM`.

```json
{
  "vessels": [
    {
      "vessel_id": "V001",
      "name": "MV Alpha",
      "eta": "2026-10-01 08:00",
      "size_teu": 5000,
      "cargo_type": "reefer",
      "priority": 1
    }
  ],
  "berths": [
    {
      "berth_id": "B1",
      "capacity_teu": 16000,
      "crane_count": 4,
      "avg_dwell_hours": 6.0
    }
  ]
}
```

Limits: 1–5,000 vessels and 1–500 berths. Response body is identical to
`GET /api/v1/plan`.

---

## `POST /api/v1/uploads/{dataset}`

`dataset` is `vessels` or `berths`. Replaces that one dataset with an uploaded
CSV and returns a freshly generated plan; the other dataset keeps its configured
values, so a vessel schedule can be iterated on without re-uploading berths.

Multipart form field: `file`. Requires a `.csv` extension, UTF-8 encoding (a BOM
is tolerated) and all required columns. The size limit is enforced while
streaming, so an oversized upload is rejected without being fully read into
memory.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/uploads/vessels \
  -F "file=@my-schedule.csv"
```

---

## `GET /api/v1/templates/{dataset}`

Returns the configured sample dataset as CSV, restricted to exactly the required
columns, as `sample_vessels.csv` or `sample_berths.csv`.

---

## `GET /api/v1/plan/export.csv`

Flattens the plan to one row per vessel for spreadsheets or a TOS import.
Berthed and rerouted vessels share a single schema, distinguished by `status`:

```
vessel_id,vessel_name,status,berth_id,crane_count,arrival,berth_start,departure_est,wait_hours,priority,notes
```

Rerouted rows leave the berth columns empty and carry the reason plus the ranked
alternatives in `notes`.
