# PortPulse — Container Congestion Predictor & Port Operations Optimiser

👥 Team
Field	Value
Team Name	ABC
Track	AI
Team Lead	Hetvi Taank — hetvi.taank@ibm.com
Members	Trusha Patel, Jigar Sakhia, Priyansh Sukhdia

🎯 Problem Statement
The 2021 LA/Long Beach port backlog had 100+ ships waiting offshore for weeks, costing global supply chains $10B+. Port operators allocate berths, cranes, and yard space across hundreds of vessels manually in spreadsheets. Congestion hotspots are identified reactively — after vessels are already queuing — and alternate routing decisions come too late to help shift supervisors mitigate delays.

💡 Solution
PortPulse is an AI-assisted port operations solution that predicts congestion hotspots using vessel schedules and berth capacity data, recommends alternate routing strategies via IBM watsonx.ai reasoning, optimizes berth and crane assignments by priority, and generates a ready-to-use 72-hour port operations plan for shift supervisors. It features an interactive Ops Assistant chat widget (`/api/v1/chat`) for plain-English query answering grounded in live plan data and a stylized live nautical map.

✨ Key Features
- **72-hour congestion risk forecasting**: Predicts volume vs capacity across rolling 24-hour windows with ALSC risk level classification (HIGH, MEDIUM, LOW).
- **Priority-based automated berth & crane assignment**: Schedules incoming vessels to berths while allocating cranes based on cargo priority (P1/P2/P3), generating an auditable reason per decision.
- **AI-generated alternate port routing (IBM watsonx.ai)**: Evaluates unassigned vessels against regional alternate ports (Oakland, Tacoma, Ensenada) and leverages watsonx.ai reasoning (`ibm/granite-3-8b-instruct`) to generate plain-language reroute justifications.
- **Conversational Ops Assistant (`/api/v1/chat`)**: Interactive chat assistant grounded directly in live plan data, answering queries on congestion risk, berth allocation, and unassigned vessels.
- **Side-Panel Admin Dashboard & Live Nautical Map**: Professional ops tool UI featuring tabbed navigation (Dashboard, Berth Allocation, Reallocation & Routing, Vessel Map), CSV upload/export controls, and interactive SVG schematic vessel map with hover tooltips.

🛠️ Tech Stack
Category	Technologies
Languages	Python, JavaScript, HTML5, CSS3
Frameworks	FastAPI, Pydantic
IBM Technologies	IBM watsonx.ai (Granite 3 models), IBM Bob
Databases	File-based CSV Datasets (Vessels & Berths)
Other	Uvicorn, Pytest, Ruff, Mypy, Docker, GitHub Actions

📁 Repository Structure
├── src/                      # Source code directory
│   └── portpulse/            # PortPulse core package
│       ├── api/              # FastAPI endpoints (plan, datasets, health, security)
│       ├── data/             # Bundled CSV datasets (vessels.csv, berths.csv)
│       ├── domain/           # Core logic (planner, prediction, routing, chat, summary)
│       ├── integrations/     # IBM watsonx.ai REST client integration
│       └── static/           # Operations dashboard (index.html)
├── docs/                     # Documentation files
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   ├── api.md
│   └── setup-guide.md
├── demo/                     # Demo artifacts
│   ├── screenshots/          # App screenshots
│   ├── demo-video-link.txt   # Link to demo video
│   └── live-demo-url.txt     # Link to live demo
├── presentation/             # Slide deck and presentation materials
├── scripts/                  # Utility scripts (e.g., sample data generator)
├── tests/                    # Pytest test suite (168 tests)
├── requirements.txt          # Python dependencies
├── pyproject.toml            # Tooling and package configuration
├── Dockerfile                # Container deployment spec
└── submission.yaml           # Hackathon submission metadata

⚡ How to Run
# 1. Clone the repo
git clone https://github.com/Jigar-CS/bob-ai-hackathon-ABC.git
cd bob-ai-hackathon-ABC

# 2. Install dependencies (Python 3.10+ recommended)
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment (optional: for IBM watsonx.ai integration)
cp .env.example .env
# Edit .env with your WATSONX_API_KEY, WATSONX_PROJECT_ID, and WATSONX_URL if available

# 4. Start the PortPulse application server
python -m portpulse

# 5. Access the dashboard
# Open http://127.0.0.1:8000 in your web browser

# 6. Run automated test suite (168 tests)
pytest tests/

🖥️ Demo
Artifact	Link
📹 Demo Video	See demo/demo-video-link.txt
🌐 Live Demo	See demo/live-demo-url.txt
🖼️ Screenshots	See demo/screenshots/
📊 Presentation	See presentation/

⚠️ Known Limitations
- **Greedy heuristic planner**: The berth scheduler uses a greedy priority-first heuristic rather than full mixed-integer linear programming (MILP) or global mathematical optimization.
- **Synthetic CSV input**: Operates on structured CSV datasets (vessels and berths) rather than live real-time AIS marine telemetry feeds or live port terminal operating system (TOS) APIs.
- **Fixed candidate pool for routing**: Alternate port routing evaluates a fixed set of regional candidate ports (Port of Oakland, Port of Tacoma, Port of Ensenada) based on distance and draft capacity.

🏅 What We're Most Proud Of
We focused on an end-to-end, evidence-grounded workflow from raw vessel schedules to a single actionable 72-hour operations plan. AI reasoning via IBM watsonx.ai is applied specifically where it adds tangible value — explaining complex rerouting trade-offs and answering shift supervisors' operational queries in plain English — rather than as a decorative wrapper. We built a robust domain-driven backend with 100% test coverage across 168 tests, a clean contract architecture for IBM Bob integration, and a responsive, tabbed admin dashboard with interactive nautical chart visualizations.
