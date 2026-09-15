# PortPulse — Container Congestion Predictor & Port Operations Optimiser

[![CI](https://github.com/Jigar-CS/bob-ai-hackathon-ABC/actions/workflows/ci.yml/badge.svg)](https://github.com/Jigar-CS/bob-ai-hackathon-ABC/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | ABC |
| **Track** | AI |
| **Category** | Logistics & Ports — L1 Container Congestion Predictor & Port Operations Optimiser |
| **Team Lead** | Hetvi Tank — `hetvitaank07@gmail.com` |
| **Members** | Trusha Patel, Jigar Sakhia, Priyansh Sukhdia |

---

## 🎯 Problem Statement

The 2021 LA/Long Beach port backlog had 100+ ships waiting offshore for weeks, costing global supply chains over $10 Billion. Today, port operators allocate berths, cranes, and yard space across hundreds of incoming vessels manually in spreadsheets. Congestion hotspots are identified reactively — after vessels are already queuing in deep water — and alternate port routing decisions come too late for shift supervisors to take preventative action. Every hour of delay ripples across regional logistics networks, compounding berth conflicts, demurrage penalties, and fuel burn.

---

## 💡 Solution

**PortPulse** is an AI-assisted port operations solution that predicts congestion hotspots using vessel arrival schedules and berth capacity data, recommends alternate routing strategies via IBM watsonx.ai reasoning, optimizes berth and crane assignments by priority, and generates a ready-to-use 72-hour port operations plan for shift supervisors.

It combines a domain-driven Python planning engine with **IBM watsonx.ai** (`ibm/granite-3-8b-instruct`), an interactive Ops Assistant chat widget (`/api/v1/chat`), and a professional side-panel admin dashboard featuring an interactive SVG live nautical chart.

---

## ✨ Key Features

- **72-Hour Congestion Risk Forecasting**: Buckets incoming arrivals into rolling 24-hour windows from earliest ETA, comparing incoming TEU against total berth capacity to classify windows as LOW, MEDIUM, or HIGH risk (ALSC risk model).
- **Priority-Based Automated Berth & Crane Allocation**: Sorts vessels by cargo priority (P1/P2/P3), allocating berths and cranes to minimize queue wait time while recording a deterministic, auditable single-line reason for every placement.
- **AI-Generated Alternate Port Routing (IBM watsonx.ai)**: Ranks regional candidate ports (Oakland, Tacoma, Ensenada) by distance and draft fit for unassigned vessels, leveraging IBM watsonx.ai (`ibm/granite-3-8b-instruct`) to generate plain-language reroute justifications for ship captains.
- **Conversational Ops Assistant (`/api/v1/chat`)**: Slide-out chat assistant grounded directly in live 72-hour plan data, featuring pre-LLM scope gating (filtering off-topic questions) and strict system-prompt security guardrails against prompt injection.
- **Side-Panel Admin Dashboard & Live Nautical Map**: Professional ops tool UI featuring tabbed navigation (Dashboard, Berth Allocation, Reallocation & Routing, Vessel Map), top-mounted CSV upload/export controls, and interactive SVG schematic vessel map with hover tooltips.
- **Resilient Fallback Architecture**: Isolated engine execution ensures watsonx.ai API failures or missing keys degrade gracefully to structured template text without ever failing plan generation or returning HTTP 500 errors.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | Python 3.10+, JavaScript (ES6+), HTML5, CSS3 |
| **Frameworks** | FastAPI, Pydantic v2 |
| **IBM Technologies** | IBM watsonx.ai (`ibm/granite-3-8b-instruct`), IBM Bob |
| **Databases / Storage** | File-based CSV Datasets (`vessels.csv` & `berths.csv`) |
| **DevOps & Tooling** | Uvicorn, Docker, GitHub Actions CI/CD, Pytest (168 tests), Ruff, Mypy |

---

## 📁 Repository Structure

```text
├── src/                      # Source code directory
│   └── portpulse/            # PortPulse core package
│       ├── api/              # FastAPI endpoints (plan, datasets, health, security)
│       ├── data/             # Bundled CSV datasets (vessels.csv, berths.csv)
│       ├── domain/           # Framework-free core logic (planner, prediction, assignment, routing, chat, summary)
│       ├── integrations/     # IBM watsonx.ai REST client (IAM auth, retries, circuit breaker)
│       └── static/           # Operations dashboard single-file frontend (index.html)
├── docs/                     # Comprehensive written documentation
│   ├── problem-statement.md  # Detailed domain problem analysis
│   ├── solution-overview.md  # End-to-end system architectural overview
│   ├── architecture.md       # Layered design, data flow & security posture
│   ├── api.md                # Full OpenAPI specification & error taxonomy
│   └── setup-guide.md        # Local, Docker, and environment setup guide
├── demo/                     # Hackathon demo artifacts
│   ├── screenshots/          # High-resolution application screenshots
│   ├── demo-video-link.txt   # Link to demo video recording
│   └── live-demo-url.txt     # Link to live deployed application
├── presentation/             # Slide deck and presentation materials
├── scripts/                  # Utility scripts (e.g., generate_50_samples.py)
├── tests/                    # Pytest test suite (168 tests, >93% coverage)
├── requirements.txt          # Python runtime dependencies
├── pyproject.toml            # Tooling configuration (Ruff, Mypy, Pytest, Coverage)
├── Dockerfile                # Multi-stage container build spec
└── submission.yaml           # Structured hackathon submission metadata
```

---

## ⚡ How to Run

```bash
# 1. Clone the repository
git clone https://github.com/Jigar-CS/bob-ai-hackathon-ABC.git
cd bob-ai-hackathon-ABC

# 2. Create and activate a virtual environment (Python 3.10+ recommended)
python -m venv .venv
source .venv/bin/activate          # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables (Optional: for IBM watsonx.ai integration)
cp .env.example .env
# Edit .env to set WATSONX_API_KEY, WATSONX_PROJECT_ID, and WATSONX_URL (or BOB_AGENT_API_KEY)
# Note: If credentials are not provided, PortPulse seamlessly uses smart template fallbacks!

# 5. Start the PortPulse application server
python -m portpulse

# 6. Access the web dashboard & API docs
# Web Dashboard:        http://127.0.0.1:8000
# Interactive API Docs: http://127.0.0.1:8000/api/docs

# 7. Run automated verification test suite (168 tests)
pytest tests/
```

---

## 🖥️ Demo

| Artifact | Link |
|---|---|
| **📹 Demo Video** | [demo/demo-video-link.txt](demo/demo-video-link.txt) |
| **🌐 Live Demo** | [demo/live-demo-url.txt](demo/live-demo-url.txt) |
| **🖼️ Screenshots** | [demo/screenshots/](demo/screenshots/) |
| **📊 Presentation** | [presentation/](presentation/) |

---

## ⚠️ Known Limitations

- **Greedy Priority-First Allocator**: The berth scheduler uses a greedy priority-first placement heuristic rather than global Mixed-Integer Linear Programming (MILP). While fast, explainable, and deterministic, it may not find the global mathematical optimum.
- **Synthetic CSV Datasets**: Operates on structured synthetic CSV datasets (`vessels.csv` and `berths.csv`) rather than a live real-time AIS marine satellite telemetry stream or Terminal Operating System (TOS) API feed.
- **Fixed Candidate Port Pool**: Alternate port routing recommendations evaluate a fixed regional candidate pool (Port of Oakland, Port of Tacoma, Port of Ensenada) based on draft capacity and nautical distance.

---

## 🏅 What We're Most Proud Of

- **Honest, Evidence-Grounded AI**: We applied AI reasoning via IBM watsonx.ai (`ibm/granite-3-8b-instruct`) specifically where human language adds genuine value — explaining complex rerouting trade-offs and answering shift supervisors' operational queries in plain English — rather than as a decorative wrapper over numeric data.
- **Zero-Downtime Fallback Design**: Isolated engine execution ensures that watsonx.ai rate limits, missing keys, or network failures instantly degrade to clean, structured template text without ever breaking the 72-hour ops plan or returning HTTP 500 errors.
- **Clean Architecture & 100% Test Pass Rate**: Built a framework-free domain layer with 168 unit and API integration tests (>93% coverage), strict security posture (HMAC API key auth, streaming upload limits, CSP headers, rate limiting), and a responsive admin dashboard featuring interactive SVG nautical chart visualisations.
