# PortPulse — System Architecture & Design Specification

## Overview

PortPulse is built on a clean, layered architecture with strict inward dependency rules. The domain layer contains zero web framework code and can execute in complete isolation. The API layer (FastAPI) handles request routing, validation, security headers, rate limiting, and HTTP error mapping.

---

## 🏗️ System Layer Architecture (Mermaid)

```mermaid
graph TD
    User["Shift Operations Supervisor / User"]
    
    subgraph Frontend["Frontend Layer (static/index.html)"]
        Dashboard["Side-Panel Admin Dashboard"]
        KpiStrip["KPI Tracking Strip"]
        SwapVisual["Top 5 Swap Optimizer Card"]
        WhatIfPanel["What-If Scenario Simulator Panel"]
        CascadePanel["Cascading Impact Simulator Panel"]
        NauticalMap["Interactive SVG Nautical Chart"]
        ChatWidget["AI Ops Assistant Floating Widget"]
    end

    subgraph API["FastAPI REST API Layer (portpulse/api)"]
        HealthRoute["GET /health"]
        PlanRoute["GET /api/v1/plan"]
        WhatIfRoute["POST /api/v1/plan/whatif"]
        CascadeRoute["POST /api/v1/cascade-simulation"]
        ChatRoute["POST /api/v1/chat"]
        DataRoutes["POST /api/v1/uploads/* & GET /templates"]
    end

    subgraph Domain["Framework-Free Domain Layer (portpulse/domain)"]
        Planner["planner.py (Orchestrator)"]
        Prediction["prediction.py (ALSC Horizon)"]
        Assignment["assignment.py (Greedy Allocator)"]
        KpiCalc["kpi_calculator.py (Metrics)"]
        SwapOpt["swap_optimizer.py (Swap Advisory)"]
        WhatIfSim["whatif_simulator.py (Sandboxed Diff)"]
        CascadeSim["cascade_simulator.py (Ripple Engine)"]
        Routing["routing.py (Alternate Ports)"]
        ChatEngine["chat.py (Scope Gate + Context)"]
        SummaryEngine["summary.py (Shift Summary)"]
    end

    subgraph External["External Services & Datasets"]
        Watsonx["integrations/watsonx.py Client"]
        WatsonxAI["IBM watsonx.ai (ibm/granite-3-8b-instruct)"]
        CSVData["File Datasets (vessels.csv & berths.csv)"]
    end

    User -->|"Interacts with UI"| Dashboard
    Dashboard --> KpiStrip
    Dashboard --> SwapVisual
    Dashboard --> WhatIfPanel
    Dashboard --> CascadePanel
    Dashboard --> NauticalMap
    Dashboard --> ChatWidget

    Dashboard -->|"fetch /api/v1/plan"| PlanRoute
    WhatIfPanel -->|"POST /plan/whatif"| WhatIfRoute
    CascadePanel -->|"POST /cascade-simulation"| CascadeRoute
    ChatWidget -->|"POST /chat"| ChatRoute
    Dashboard --> DataRoutes

    PlanRoute --> Planner
    WhatIfRoute --> WhatIfSim
    CascadeRoute --> CascadeSim
    ChatRoute --> ChatEngine

    Planner --> Prediction
    Planner --> Assignment
    Planner --> KpiCalc
    Planner --> SwapOpt
    Planner --> Routing
    Planner --> SummaryEngine

    WhatIfSim --> Planner
    CascadeSim --> Planner

    Prediction --> CSVData
    Assignment --> CSVData
    Routing --> Watsonx
    ChatEngine --> Watsonx
    SummaryEngine --> Watsonx

    Watsonx -->|"REST (IAM Auth + Circuit Breaker)"| WatsonxAI
```

---

## 🔄 Cascading Impact Simulation Data Flow (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    actor User as Shift Supervisor
    participant UI as Dashboard UI
    participant API as API Layer (/cascade-simulation)
    participant Sim as cascade_simulator.py
    participant Planner as planner.py
    participant Engine as assignment.py

    User->>UI: Selects Vessel (e.g. V001) & Delay (10h)
    UI->>API: POST /api/v1/cascade-simulation {disruption, max_iterations: 5}
    API->>Sim: simulate_cascade(vessels, berths, disruption)
    Sim->>Planner: generate_ops_plan() (Pass 1: Baseline)
    Planner->>Engine: assign_berths()
    Engine-->>Sim: Returns Baseline Assignments & Start Times
    
    loop Cascade Ripple Pass (up to max_iterations)
        Sim->>Sim: Apply ETA Delays & Re-run Schedule
        Sim->>Planner: generate_ops_plan() (Pass N)
        Planner-->>Sim: Returns Modified Schedule
        Sim->>Sim: Compare Start Times vs Baseline
        alt Schedule Stabilized OR No New Hits
            Sim->>Sim: Break Loop (Stabilized = True)
        end
    end

    Sim->>Sim: Calculate Demurrage Cost ($0.05/TEU-hr)
    Sim-->>API: Returns {iterations_run, total_estimated_cost, affected_vessels}
    API-->>UI: HTTP 200 OK Response
    UI->>User: Renders Headline Cost ($23,622.00) & Waterfall Timeline
```

---

## 🛠️ Components & Module Responsibilities

| Component | Module | Responsibility |
|---|---|---|
| **Application Factory** | `app.py` | Builds FastAPI app instance, registers CORS middleware, rate limiters, security headers, and static mount (`/`). |
| **Configuration** | `config.py` | Environment settings validator using Pydantic Settings across `PORTPULSE_*` and `WATSONX_*` namespaces. |
| **Schemas** | `schemas.py` | Data contracts (`OpsPlan`, `BerthAssignment`, `SwapOpportunity`, `CascadeRequest`, `WhatIfRequest`, `KpiSummary`). |
| **Congestion Engine** | `domain/prediction.py` | Buckets arrivals into 24h rolling windows and computes ALSC risk levels (LOW, MEDIUM, HIGH). |
| **Assignment Engine** | `domain/assignment.py` | Priority-first greedy berth and crane allocation algorithm with deterministic decision reasons. |
| **KPI Calculator** | `domain/kpi_calculator.py` | Computes average wait hours, berth utilization %, vessels at risk, and CO2 emissions saved. |
| **Swap Optimizer** | `domain/swap_optimizer.py` | Identifies pairwise berth swaps to reduce P1 queue wait times and calculates demurrage cost savings. |
| **What-If Simulator** | `domain/whatif_simulator.py` | Sandboxed simulation engine comparing baseline vs scenario diffs without mutating live data. |
| **Cascade Simulator** | `domain/cascade_simulator.py` | Multi-pass schedule ripple engine tracing downstream delays and financial demurrage impact. |
| **Routing Engine** | `domain/routing.py` | Ranks regional alternate ports (distance/fit) and uses IBM watsonx.ai to generate plain-language justifications. |
| **Conversational Assistant** | `domain/chat.py` | Scope-gated AI assistant answering operator questions grounded in live 72-hour ops plan data. |
| **watsonx.ai Client** | `integrations/watsonx.py` | IAM authentication, token caching, exponential retries with jitter, and circuit breaker fallback. |

---

## 🖼️ Architecture & Workflow Visual Diagrams

- **[Tech Stack Flowchart](images/tech_stack_flowchart.svg)**: Complete breakdown of presentation, web server, domain engine, and IBM watsonx.ai integration layers.
- **[Website & Dashboard Feature Map](images/website_feature_flowchart.svg)**: Map of side-panel navigation layout, 4 tabs, simulation controls, and floating chat assistant.
- **[Cascading Impact Simulation Workflow](images/cascading_simulation_workflow.svg)**: Detailed step-by-step workflow of multi-pass schedule ripple analysis.

---

## 🔒 Security Posture

| Security Dimension | Implementation |
|---|---|
| **Authentication** | `X-API-Key` header verified via `hmac.compare_digest` for write endpoints (`/plan/custom`, `/uploads/*`, `/chat`). |
| **Prompt Injection Defense** | Pre-LLM keyword scope gate rejects off-topic queries; vessel input text is stripped of control characters and length-capped. |
| **Rate Limiting** | Sliding 60-second window rate limiter (30 req/min per IP) on POST endpoints. |
| **HTTP Security Headers** | Injects `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`. |
| **Zero-Downtime Fallback** | Isolated engine execution degrades watsonx.ai network or auth failures to structured template text without returning 500 errors. |
