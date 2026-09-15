# Setup Guide

Everything needed to run, configure and deploy PortPulse.

## Prerequisites

- Python 3.10 or newer
- pip
- Docker (optional, for the container route)
- IBM watsonx.ai or BOB Agent credentials (optional; enables AI-written routing text and the conversational assistant)

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
cp src/.env.example .env
```

Every setting has a working default, so an empty `.env` is valid. Environment
variables always take precedence over `.env`. The application searches for `.env`
in the repository root, `src/`, and the parent directory — whichever is found first
is loaded.

### IBM watsonx.ai / BOB Agent

The application accepts credentials from either the `WATSONX_*` or `BOB_AGENT_*`
variable families. Both resolve to the same settings fields; whichever is non-empty
is used. `BOB_AGENT_*` is checked first.

**BOB Agent variables (preferred for IBM Bob deployments):**

| Variable | Default | Notes |
|---|---|---|
| `BOB_AGENT_API_KEY` | *(unset)* | Alias for `WATSONX_API_KEY`. Enables AI routing text and chat. |
| `BOB_AGENT_PROJECT_ID` | `"bob-agent-project"` | Alias for `WATSONX_PROJECT_ID`. Defaults to `"bob-agent-project"` when the API key is set but this is blank. |
| `BOB_AGENT_URL` | `https://us-south.ml.cloud.ibm.com` | Alias for `WATSONX_URL`. |

**watsonx.ai variables (standard IBM Cloud credentials):**

| Variable | Default | Notes |
|---|---|---|
| `WATSONX_API_KEY` | *(unset)* | IBM Cloud API key. Enables AI routing text and chat. Without it, template text is used. |
| `WATSONX_PROJECT_ID` | *(unset)* | Required alongside the API key. |
| `WATSONX_URL` | `https://us-south.ml.cloud.ibm.com` | Regional endpoint. Change for `eu-de` or `jp-tok` deployments. |
| `WATSONX_MODEL_ID` | `ibm/granite-3-8b-instruct` | Any watsonx.ai text-generation model. |
| `WATSONX_API_VERSION` | `2024-05-01` | watsonx.ai REST API version string. |
| `WATSONX_IAM_URL` | `https://iam.cloud.ibm.com/identity/token` | IBM IAM token endpoint. |
| `WATSONX_IAM_TIMEOUT_SECONDS` | `10` | Timeout for IAM token requests. |
| `WATSONX_REQUEST_TIMEOUT_SECONDS` | `60` | Generation call timeout. |
| `WATSONX_MAX_RETRIES` | `3` | Retries on 429 and 5xx responses. |
| `WATSONX_BACKOFF_FACTOR` | `0.5` | Exponential backoff base (with jitter). |
| `WATSONX_MAX_NEW_TOKENS` | `300` | Maximum tokens to generate per call. |
| `WATSONX_AUTH_COOLDOWN_SECONDS` | `60` | Circuit-breaker window after an auth failure. |
| `WATSONX_TOKEN_EXPIRY_BUFFER_SECONDS` | `300` | Renew the IAM token this many seconds before it expires. |

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
| `PORTPULSE_API_KEY` | *(unset)* | When set, write endpoints (`POST /plan/custom`, `POST /uploads/*`, `POST /chat`) require an `X-API-Key` header. |
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

To also enable AI features with Compose:

```bash
PORTPULSE_API_KEY=choose-a-strong-value \
BOB_AGENT_API_KEY=your-ibm-api-key \
docker compose up --build
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
| Reroute text is generic rather than AI-written | `WATSONX_API_KEY` / `BOB_AGENT_API_KEY` is unset or a placeholder. Check the startup log line about watsonx configuration. |
| Chat replies are structured text, not natural language | Same as above — watsonx.ai is not configured. The rule-based fallback is active. |
| `401 Invalid or missing API key` | `PORTPULSE_API_KEY` is set; send it in the `X-API-Key` header on write endpoints. |
| `429 Rate limit exceeded` | More than 30 POSTs per minute from one IP. Wait 60 seconds and retry. |
| Startup fails with `PORTPULSE_API_KEY must be set` | Expected in production mode. Set the key, or use `PORTPULSE_ENVIRONMENT=development` locally. |
| `413` on upload | The file exceeds `PORTPULSE_MAX_UPLOAD_BYTES`. |
| Port 8000 already in use | `uvicorn portpulse.main:app --port 8001`. |
| Dashboard loads but shows stale numbers | The plan is computed per request; reload the page or use the data upload to refresh. |
