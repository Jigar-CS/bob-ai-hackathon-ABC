# src/ — PortPulse Source Code

All application source code lives in this directory.

## Layout

```
src/
├── .env.example          ← Template for every environment variable the app reads
├── README.md             ← This file
└── portpulse/            ← Installable Python package (pip install -e .)
    ├── api/              ← HTTP route handlers (health, plan, datasets)
    ├── domain/           ← Framework-free planning logic (prediction, assignment, routing)
    ├── integrations/     ← IBM watsonx.ai REST client
    ├── data/             ← Bundled sample datasets (vessels.csv, berths.csv, alternate_ports.json)
    ├── static/           ← Single-file operations dashboard (index.html, no build step)
    ├── app.py            ← FastAPI application factory
    ├── config.py         ← Typed settings via pydantic-settings
    ├── schemas.py        ← Request / response models and OpenAPI contract
    ├── datasets.py       ← Dataset access layer (swap for DB / live feed here)
    ├── csv_io.py         ← CSV reading, validation and serialisation helpers
    ├── errors.py         ← Domain exception hierarchy (no HTTPException below api/)
    ├── security.py       ← Optional API-key guard for write endpoints
    ├── middleware.py     ← Request correlation IDs and access logging
    ├── logging_setup.py  ← Structured logging (console or JSON)
    ├── constants.py      ← Shared data-contract constants
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
local development without watsonx.ai credentials.

```bash
cp src/.env.example .env
```

See `.env.example` for a description of every variable.

## Tests

```bash
pytest              # all tests
pytest tests/api/   # API layer only
pytest tests/domain # domain logic only
```

Tests never make real network calls. watsonx.ai credentials are blanked in
`conftest.py`, so tests pass with or without a configured `.env`.
