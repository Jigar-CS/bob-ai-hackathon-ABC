# src/ — PortPulse Source Code

All application source code lives in this directory.

## Layout

```
src/
├── .env.example          ← Template for every environment variable the app reads
├── README.md             ← This file
└── portpulse/            ← Installable Python package (pip install -e .)
    ├── api/              ← HTTP route handlers (health, plan, datasets)
    ├── domain/           ← Framework-free planning logic
    │   ├── assignment.py ← Priority-first greedy berth allocator
    │   ├── chat.py       ← Conversational ops assistant (scope guard + LLM + fallback)
    │   ├── planner.py    ← Orchestration: runs engines, isolates failures into warnings
    │   ├── prediction.py ← Rolling 24-hour congestion forecast
    │   ├── routing.py    ← Alternate-port ranking, LLM prompting, reply parsing
    │   └── summary.py    ← 3–4 sentence shift summary (AI or template)
    ├── integrations/     ← IBM watsonx.ai REST client (IAM auth, retries, circuit breaker)
    ├── data/             ← Bundled sample datasets (vessels.csv, berths.csv, alternate_ports.json)
    ├── static/           ← Single-file operations dashboard (index.html, no build step)
    ├── app.py            ← FastAPI application factory
    ├── config.py         ← Typed settings via pydantic-settings (PORTPULSE_* and WATSONX_*/BOB_AGENT_*)
    ├── schemas.py        ← Request / response models and OpenAPI contract
    ├── datasets.py       ← Dataset access layer (swap for DB / live feed here)
    ├── csv_io.py         ← CSV reading, validation and serialisation helpers
    ├── errors.py         ← Domain exception hierarchy (no HTTPException below api/)
    ├── security.py       ← Optional API-key guard for write endpoints
    ├── middleware.py     ← Request IDs, security headers (CSP, HSTS, X-Frame-Options), rate limiting
    ├── logging_setup.py  ← Structured logging (console or JSON)
    ├── constants.py      ← Shared data-contract constants (column names, timestamp format)
    ├── main.py           ← ASGI entry point
    └── __main__.py       ← Console entry point (python -m portpulse)
```

## Quick start

```bash
# From the repository root:
pip install -e ".[dev]"
uvicorn portpulse.main:app --reload
```

Open <http://127.0.0.1:8000>. Full instructions are in [../docs/setup-guide.md](../docs/setup-guide.md).

## Environment variables

Copy `.env.example` to `.env` (one level up, at the repository root) and fill in
your values. Every variable has a working default — an empty `.env` is valid for
local development without AI credentials.

```bash
cp src/.env.example .env
```

### IBM watsonx.ai / BOB Agent

Both variable families are interchangeable. The application resolves them in the
order shown; the first non-placeholder value found is used.

| Variable | Equivalent to |
|---|---|
| `BOB_AGENT_API_KEY` | `WATSONX_API_KEY` |
| `BOB_AGENT_PROJECT_ID` | `WATSONX_PROJECT_ID` (defaults to `"bob-agent-project"` if omitted) |
| `BOB_AGENT_URL` | `WATSONX_URL` |

See `.env.example` for the full list of tunable watsonx.ai variables
(`WATSONX_MAX_RETRIES`, timeouts, token limits, etc.).

## Tests

```bash
pytest              # all tests
pytest tests/api/   # API layer only
pytest tests/domain # domain logic only
pytest tests/integrations # watsonx client only
```

Tests never make real network calls. watsonx.ai credentials are blanked in
`conftest.py`, so tests pass with or without a configured `.env`. Each test
receives a temporary dataset directory via the `data_dir` fixture so no test
reads the bundled sample data.
