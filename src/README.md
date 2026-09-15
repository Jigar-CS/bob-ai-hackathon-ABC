# src/ — PortPulse Source Code Layout

All application source code lives in this directory.

## Layout

```text
src/
├── .env.example                ← Template for every environment variable the app reads
├── README.md                   ← This file
└── portpulse/                  ← Installable Python package (pip install -e .)
    ├── api/                    ← HTTP route handlers (health, plan, datasets, security)
    ├── domain/                 ← Framework-free planning and simulation logic
    │   ├── assignment.py       ← Priority-first greedy berth allocator
    │   ├── kpi_calculator.py   ← Real-time summary KPIs (avg wait, utilization %, CO2 saved)
    │   ├── swap_optimizer.py   ← Top 5 advisory berth swap optimizer
    │   ├── whatif_simulator.py ← Sandboxed scenario simulation engine
    │   ├── cascade_simulator.py← Multi-pass queue ripple & demurrage cost simulator
    │   ├── chat.py             ← Conversational ops assistant (scope guard + LLM + fallback)
    │   ├── planner.py          ← Orchestration: runs engines, isolates failures into warnings
    │   ├── prediction.py       ← Rolling 24-hour congestion forecast (ALSC)
    │   ├── routing.py          ← Alternate-port ranking, LLM prompting, reply parsing
    │   └── summary.py          ← 3–4 sentence shift summary (AI or template)
    ├── integrations/           ← IBM watsonx.ai REST client (IAM auth, retries, circuit breaker)
    ├── data/                   ← Bundled sample datasets (vessels.csv, berths.csv, alternate_ports.json)
    ├── static/                 ← Single-file operations dashboard (index.html, no build step)
    ├── app.py                  ← FastAPI application factory
    ├── config.py               ← Typed settings via pydantic-settings (PORTPULSE_* and WATSONX_*/BOB_AGENT_*)
    ├── schemas.py              ← Request / response models and OpenAPI contract
    ├── datasets.py             ← Dataset access layer (swap for DB / live feed here)
    ├── csv_io.py               ← CSV reading, validation and serialisation helpers
    ├── errors.py               ← Domain exception hierarchy (no HTTPException below api/)
    ├── security.py             ← Optional API-key guard for write endpoints
    ├── middleware.py           ← Request IDs, security headers (CSP, HSTS, X-Frame-Options), rate limiting
    ├── logging_setup.py        ← Structured logging (console or JSON)
    ├── constants.py            ← Shared data-contract constants (column names, timestamp format)
    ├── main.py                 ← ASGI entry point
    └── __main__.py             ← Console entry point (python -m portpulse)
```

## Quick start

```bash
# From the repository root:
pip install -e ".[dev]"
python -m portpulse
```

Open <http://127.0.0.1:8000>. Full instructions are in [../docs/setup-guide.md](../docs/setup-guide.md).

## Tests

```bash
pytest tests/                   # 180 tests, 100% pass rate
```
