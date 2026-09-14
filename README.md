# PortPulse

Container-port congestion prediction and 72-hour berth operations planning, with
IBM watsonx.ai reasoning for vessels that cannot be berthed.

[![CI](https://github.com/Jigar-CS/bob-ai-hackathon-ABC/actions/workflows/ci.yml/badge.svg)](https://github.com/Jigar-CS/bob-ai-hackathon-ABC/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

PortPulse takes a vessel arrival schedule and a berth capacity table, then answers
three questions a shift supervisor asks every shift:

1. **Which upcoming windows will exceed berth capacity?** Vessels are bucketed into
   rolling 24-hour windows and arriving TEU is compared against total capacity.
2. **Which vessel goes to which berth, and when?** A priority-first greedy allocator
   places each vessel at the berth that frees up earliest, and records a one-line,
   auditable reason for every decision.
3. **Where should the vessels we cannot take go instead?** Alternate ports are ranked
   by capacity fit and distance, and IBM watsonx.ai (`ibm/granite-3-8b-instruct`)
   turns the ranking into a plain-language recommendation.

Everything lands on one dashboard and exports to CSV for spreadsheets or a terminal
operating system import.

---

## Team

| Field | Value |
|---|---|
| Team | ABC |
| Track | AI |
| Problem statement | L1 Container Congestion Predictor & Port Operations Optimiser |
| Lead | Hetvi Taank |
| Members | Trusha Patel, Jigar Sakhia, Priyansh Sukhdia |

---

## Quick start

```bash
git clone https://github.com/Jigar-CS/bob-ai-hackathon-ABC.git
cd bob-ai-hackathon-ABC

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
uvicorn portpulse.main:app --reload
```

Open <http://127.0.0.1:8000>. The interactive API reference is at
<http://127.0.0.1:8000/api/docs>.

watsonx.ai credentials are optional. Without them the routing engine produces
structured template text instead of AI-written reasoning; nothing else changes.
To enable it, copy `.env.example` to `.env` and set `WATSONX_API_KEY` and
`WATSONX_PROJECT_ID`.

Docker:

```bash
docker build -t portpulse:local .
docker run --rm -p 8000:8000 -e PORTPULSE_ENVIRONMENT=development portpulse:local
```

Full instructions, including every configuration variable, are in
[docs/setup-guide.md](docs/setup-guide.md).

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness and readiness; 503 when datasets are unreadable |
| `GET` | `/api/v1/plan` | Full operations plan from the bundled datasets |
| `POST` | `/api/v1/plan/custom` | Plan from validated JSON in the request body |
| `GET` | `/api/v1/plan/export.csv` | Flat CSV, one row per vessel |
| `POST` | `/api/v1/uploads/{vessels\|berths}` | Replace one dataset with a CSV and replan |
| `GET` | `/api/v1/templates/{vessels\|berths}` | Sample CSV showing the expected columns |

Write endpoints require an `X-API-Key` header when `PORTPULSE_API_KEY` is set.
See [docs/api.md](docs/api.md) for payloads and error codes.

---

## Project layout

```
├── src/portpulse/          # Application package
│   ├── api/                # HTTP routes (health, plan, datasets)
│   ├── domain/             # Framework-free planning logic
│   ├── integrations/       # watsonx.ai client
│   ├── data/               # Sample vessel, berth and alternate-port datasets
│   ├── static/             # Operations dashboard (single-file, no build step)
│   ├── app.py              # Application factory
│   ├── config.py           # Typed settings
│   └── schemas.py          # Request and response models
├── tests/                  # Unit and API tests
├── scripts/                # Sample-data generator
├── docs/                   # Architecture, setup, API and problem write-ups
├── Dockerfile              # Multi-stage, non-root runtime image
└── pyproject.toml          # Packaging plus Ruff, mypy, pytest and coverage config
```

The `domain/` package imports no web framework, so the planning logic is testable
and reusable outside HTTP. The API layer translates domain exceptions into status
codes; nothing below `api/` knows about FastAPI.

---

## Development

```bash
make check     # ruff + mypy + pytest
make test-cov  # tests with a coverage report
make format    # apply Ruff autofixes and formatting
make data      # regenerate the sample datasets
```

Without `make`, run the underlying commands: `ruff check .`, `mypy`,
`pytest --cov`. CI runs lint, type-check, tests on Python 3.10–3.13, an
end-to-end HTTP smoke test, and a Docker image build.

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions.

---

## Design decisions

| Decision | Rationale |
|---|---|
| Greedy allocation rather than a linear program | Fast, deterministic, and every placement carries an explanation a supervisor can audit. A solver would be more optimal but harder to trust and to debug on shift. |
| The plan never fails because of the LLM | Each engine is isolated. watsonx.ai failures, missing credentials and unparseable replies all degrade to template text, reported in the plan's `warnings`. |
| CSV-backed datasets behind a `datasets` module | Access is wrapped in functions, so storage can become a database or a live TOS feed without touching the domain or API layers. |
| Auth opt-in, but production refuses to start without it | Keeps local use frictionless while making an unauthenticated production deployment impossible. |
| Placeholder credentials treated as unset | An unedited `.env` otherwise passes the presence check and burns retries against IBM IAM once per vessel. |

---

## Known limitations

- Greedy assignment, not full optimisation; it will not always find the
  globally best berth allocation.
- Ships with synthetic sample data rather than a live port scheduling feed.
- The alternate-port catalogue is a small illustrative list in
  `src/portpulse/data/alternate_ports.json`, not live capacity data.
- Timestamps are timezone-naive and use a single `YYYY-MM-DD HH:MM` format.
- Plans are computed per request with no caching, so `/api/v1/plan` cost grows
  with the number of unassigned vessels.

---

## Demo artefacts

| Artefact | Location |
|---|---|
| Demo video | [demo/demo-video-link.txt](demo/demo-video-link.txt) |
| Live demo | [demo/live-demo-url.txt](demo/live-demo-url.txt) |
| Screenshots | [demo/screenshots/](demo/screenshots/) |
| Slide deck | [presentation/](presentation/) |

---

## License

[MIT](LICENSE)
