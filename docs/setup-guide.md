# PortPulse — Setup & Installation Guide

Everything needed to run, configure, test, and deploy PortPulse locally or via Docker.

---

## Prerequisites

- Python 3.10 or newer
- pip
- Docker (optional, for containerized deployments)
- Google Gemini API key and/or IBM watsonx.ai credentials (optional; enables AI-written routing reasoning and chat assistant)

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Jigar-CS/bob-ai-hackathon-Team-Surfers.git
cd bob-ai-hackathon-Team-Surfers

# 2. Create & activate a virtual environment (Python 3.10+ recommended)
python -m venv .venv
source .venv/bin/activate          # On Windows PowerShell: .venv\Scripts\Activate.ps1

# 3. Install in editable development mode
pip install -e ".[dev]"
```

---

## Running locally

```bash
# Start via PortPulse CLI wrapper script
python -m portpulse
```

| Access URL | Service Served |
|---|---|
| <http://127.0.0.1:8000> | Operations Dashboard (Side-panel admin UI) |
| <http://127.0.0.1:8000/api/docs> | Interactive OpenAPI Reference |
| <http://127.0.0.1:8000/health> | Health Probe |

---

## Configuration

Copy the sample environment file and edit as needed:

```bash
cp .env.example .env
```

### Google Gemini API & IBM watsonx.ai Credentials

Set `GEMINI_API_KEY` (from [Google AI Studio](https://aistudio.google.com/)) and/or `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, and `WATSONX_URL` (or `BOB_AGENT_API_KEY` / `BOB_AGENT_PROJECT_ID`). If credentials are not provided, PortPulse degrades gracefully to template fallbacks without throwing 500 errors!

---

## Testing & Code Quality

Run the full automated test suite and linters:

```bash
# Run pytest test suite (246 tests)
pytest tests/

# Run Ruff linter and code format check
ruff check .
ruff format --check .

# Run Mypy static type checker
mypy src
```

---

## Docker Deployment

```bash
# Build local container image
docker build -t portpulse:local .

# Run containerized application
docker run --rm -p 8000:8000 -e PORTPULSE_ENVIRONMENT=development portpulse:local
```

