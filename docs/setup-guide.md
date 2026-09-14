# Setup Guide

Everything needed to run, configure and deploy PortPulse.

## Prerequisites

- Python 3.10 or newer
- pip
- Docker (optional, for the container route)
- IBM watsonx.ai credentials (optional, enables AI-written routing text)

## Install

```bash
git clone https://github.com/Jigar-CS/bob-ai-hackathon-ABC.git
cd bob-ai-hackathon-ABC

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"            # drop [dev] for a runtime-only install
```

Installing the package is what makes `import portpulse` work from any directory.
There is no `PYTHONPATH` juggling and no requirement to run from a particular
working directory.

## Run

```bash
uvicorn portpulse.main:app --reload
```

Or use the console script, which reads `PORTPULSE_HOST` and `PORTPULSE_PORT`:

```bash
portpulse
```

| URL | What it serves |
|---|---|
| <http://127.0.0.1:8000> | Operations dashboard |
| <http://127.0.0.1:8000/api/docs> | Interactive OpenAPI reference |
| <http://127.0.0.1:8000/health> | Health probe |

## Configuration

Copy the template and edit as needed:

```bash
cp .env.example .env
```

Every setting has a working default, so an empty `.env` is valid. Environment
variables always take precedence over `.env`.

### IBM watsonx.ai

| Variable | Default | Notes |
|---|---|---|
| `WATSONX_API_KEY` | *(unset)* | Enables AI routing text. Without it, template text is used. |
| `WATSONX_PROJECT_ID` | *(unset)* | Required alongside the API key. |
| `WATSONX_URL` | `https://us-south.ml.cloud.ibm.com` | Regional endpoint. |
| `WATSONX_MODEL_ID` | `ibm/granite-3-8b-instruct` | Any watsonx.ai text-generation model. |
| `WATSONX_MAX_RETRIES` | `3` | Retries on 429 and 5xx responses. |
| `WATSONX_REQUEST_TIMEOUT_SECONDS` | `60` | Generation call timeout. |
| `WATSONX_AUTH_COOLDOWN_SECONDS` | `60` | Circuit-breaker window after an auth failure. |

Values that look like an unedited template (containing `your_`, `_here`, or
`changeme`) are treated as unset. This is deliberate: a placeholder key would
otherwise pass the presence check and trigger a failed IAM round trip for every
vessel before falling back.

### Runtime and security

| Variable | Default | Notes |
|---|---|---|
| `PORTPULSE_ENVIRONMENT` | `development` | `development`, `staging` or `production`. |
| `PORTPULSE_HOST` | `127.0.0.1` | Bind address for the console script. |
| `PORTPULSE_PORT` | `8000` | Bind port. |
| `PORTPULSE_LOG_LEVEL` | `INFO` | Standard logging levels. |
| `PORTPULSE_LOG_JSON` | `false` | `true` emits one JSON object per line. |
| `PORTPULSE_API_KEY` | *(unset)* | When set, write endpoints require an `X-API-Key` header. |
| `PORTPULSE_CORS_ALLOW_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Comma-separated allowlist. |
| `PORTPULSE_MAX_UPLOAD_BYTES` | `5242880` | 5 MB; enforced while streaming, not after buffering. |

In `production` the application **refuses to start** if `PORTPULSE_API_KEY` is
unset or if the CORS allowlist contains `*`.

### Planning parameters

| Variable | Default | Notes |
|---|---|---|
| `PORTPULSE_DATA_DIR` | packaged `src/portpulse/data` | Where `vessels.csv`, `berths.csv` and `alternate_ports.json` live. |
| `PORTPULSE_MAX_BERTH_WAIT_HOURS` | `12.0` | Queue tolerance before a vessel is rerouted instead. |
| `PORTPULSE_CONGESTION_HIGH_RISK_RATIO` | `0.9` | Arriving TEU / capacity above which a window is HIGH. |
| `PORTPULSE_CONGESTION_MEDIUM_RISK_RATIO` | `0.6` | Threshold for MEDIUM. |
| `PORTPULSE_ROUTING_MAX_WORKERS` | `8` | Thread-pool cap for concurrent LLM calls. |
| `PORTPULSE_ROUTING_MAX_LLM_CALLS` | `25` | Per-request LLM call budget; the remainder use template text. |

## Data

The repository ships a sample dataset at `src/portpulse/data/`. To regenerate or
resize it:

```bash
python scripts/generate_sample_data.py                          # 40 vessels, 6 berths
python scripts/generate_sample_data.py --vessels 200 --berths 12
python scripts/generate_sample_data.py --out ./tmp-data --seed 7
```

Required CSV columns:

| Dataset | Columns |
|---|---|
| `vessels.csv` | `vessel_id`, `name`, `eta`, `size_teu`, `cargo_type`, `priority` |
| `berths.csv` | `berth_id`, `capacity_teu`, `crane_count`, `avg_dwell_hours` |

`eta` must be `YYYY-MM-DD HH:MM`. `priority` is 1–5, where 1 is highest.
Download a filled-in example from `/api/v1/templates/vessels`.

## Docker

```bash
docker build -t portpulse:local .
docker run --rm -p 8000:8000 -e PORTPULSE_ENVIRONMENT=development portpulse:local
```

Or with Compose, which defaults to production mode and therefore requires an API key:

```bash
PORTPULSE_API_KEY=choose-a-strong-value docker compose up --build
```

The image runs as an unprivileged user, contains no development dependencies, and
excludes `.env` via `.dockerignore` so local credentials are never baked in.

## Development

```bash
make check      # ruff + mypy + pytest
make test-cov   # coverage report
make format     # apply autofixes and formatting
```

Tests never make network calls: watsonx credentials are explicitly blanked and
each test gets a temporary dataset directory.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ModuleNotFoundError: portpulse` | The package is not installed. Run `pip install -e .` from the repository root. |
| `/health` returns 503, dashboard shows an error | Datasets are missing. Run `python scripts/generate_sample_data.py` or check `PORTPULSE_DATA_DIR`. |
| Reroute text is generic rather than AI-written | `WATSONX_API_KEY` / `WATSONX_PROJECT_ID` are unset or placeholders. Check the startup log line about watsonx configuration. |
| `401 Invalid or missing API key` | `PORTPULSE_API_KEY` is set; send it in the `X-API-Key` header. |
| Startup fails with `PORTPULSE_API_KEY must be set` | Expected in production mode. Set the key, or use `PORTPULSE_ENVIRONMENT=development` locally. |
| `413` on upload | The file exceeds `PORTPULSE_MAX_UPLOAD_BYTES`. |
| Port 8000 already in use | `uvicorn portpulse.main:app --port 8001`. |
| Dashboard loads but shows stale numbers | The plan is computed per request; use the Reset button to refetch. |
