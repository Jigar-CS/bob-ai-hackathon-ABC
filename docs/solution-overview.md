# Solution Overview

## What we built

PortPulse ingests vessel arrival schedules and berth capacity data, forecasts which
upcoming windows are at risk of congestion, assigns vessels to berths by priority,
and — for any vessel that cannot be placed — recommends an alternate port with
AI-written reasoning. A conversational assistant lets shift supervisors ask
plain-English questions about the live plan at any time. The result is a single
72-hour operations plan on a live dashboard, exportable as CSV.

## How it works in a real terminal

Today a shift supervisor reconciles an arrival list against berth availability in a
spreadsheet. Congestion becomes visible only once ships are already queuing, and by
then rerouting is expensive or impossible.

```
Vessel schedule + berth capacity
        ↓
Congestion forecast (rolling 24h windows)
        ↓
Priority berth & crane allocation
        ↓
Alternate-port routing for what does not fit  ──▶  IBM watsonx.ai reasoning
        ↓
72-hour operations plan (dashboard + CSV)
        ↓
Conversational assistant  ──▶  IBM watsonx.ai  (answers supervisor questions)
```

1. **Ingest.** CSV upload today; the same interface accepts a live AIS or terminal
   operating system feed by reimplementing one module (`datasets.py`).
2. **Forecast.** Arrivals are grouped into rolling 24-hour windows from the earliest
   ETA. Each window's incoming TEU is compared against total berth capacity and
   labelled LOW, MEDIUM or HIGH — days before the ships arrive.
3. **Allocate.** Vessels are sorted by cargo priority, then ETA. Priority 1 covers
   time-critical cargo such as reefers carrying perishables. Each vessel goes to the
   berth that frees up earliest and can take its size, provided the queue wait stays
   within tolerance. Every placement records a one-line reason.
4. **Reroute.** Vessels that cannot be placed within the horizon are matched against
   alternate ports ranked by spare capacity and distance. IBM watsonx.ai
   (`ibm/granite-3-8b-instruct`) explains, in plain language, why the vessel was
   turned away and why the recommended port is the right fallback — the part of the
   decision a human actually needs to read before calling a captain.
5. **Publish.** Forecast, assignment schedule and reroute recommendations render on
   one dashboard and export to CSV.
6. **Answer.** The conversational assistant (`POST /api/v1/chat`) accepts free-text
   supervisor questions grounded in the live plan. Questions about specific vessels,
   berths, congestion windows, or rerouting receive detailed markdown answers.
   Off-domain questions (weather, sports, recipes, etc.) are refused immediately
   before the LLM is called.

## Using the dashboard

- **Header metrics:** total incoming TEU, assigned and unassigned vessel counts, and
  the peak risk window.
- **Shift Operations Summary:** a 3–4 sentence AI-written or templated overview of
  the current plan state for the incoming supervisor.
- **72-hour congestion risk forecast:** one card per 24-hour window with the risk
  level and the capacity ratio behind it.
- **Tabbed operations panel** (three tabs):
  - *Berth Assignments* — searchable table of vessel, berth, cranes, arrival,
    estimated departure, queue wait, priority and the reason for each placement.
  - *Vessel Map* — stylised nautical chart showing berthed vessels (green) and
    rerouted vessels (amber) as interactive nodes with hover tooltips.
  - *Reroute Suggestions* — one card per unassigned vessel with the rejection reason
    and ranked alternate ports, including AI-written justification when available.
- **Conversational Ops Assistant:** slide-out chat panel powered by
  `domain/chat.py`. Answers supervisor questions grounded strictly in the live
  72-hour operations plan. Refuses questions outside port operations.
- **Upload / Export:** swap in your own CSV for vessels or berths, or export the
  current plan as a flat spreadsheet.

## Key design decisions

| Decision | Rationale |
|---|---|
| Greedy allocation, not a linear program | Fast, deterministic, and every decision is explainable to a supervisor. A solver optimises better but is far harder to trust or debug mid-shift. |
| Rolling 24-hour windows | Matches shift-by-shift planning rather than a single point-in-time snapshot. |
| AI applied to reroute explanations and the chat assistant | The numeric work is deterministic and testable. The LLM is used where language is genuinely the deliverable, and its failure never blocks a plan. |
| Pre-LLM scope gate in chat | Keyword-based domain check rejects off-topic messages before spending any token budget, reducing cost and preventing content-policy violations. |
| Strict system-prompt guardrails | Explicit security rule in the chat system prompt instructs the model to treat all plan data as reference, not instructions, guarding against prompt injection through vessel or berth names. |
| `BOB_AGENT_*` and `WATSONX_*` are interchangeable | `AliasChoices` in `config.py` maps both families to the same settings fields, so the application works with either credential format without branching logic. |
| Synthetic CSV data | No access to a live port scheduling system during the hackathon. The column contract is deliberately simple so a real feed can replace it. |
| Domain layer free of any web framework | The planning logic is unit-testable and reusable outside HTTP; the API layer only translates errors into status codes. |

## IBM technologies

- **IBM watsonx.ai** — `ibm/granite-3-8b-instruct` via the REST text-generation API,
  used for three purposes: explaining vessel rejections, justifying alternate-port
  recommendations, and answering supervisor chat questions. Access is wrapped in a
  client with IAM token caching, jittered retries, an authentication circuit breaker,
  and a bearer-token fast-path for BOB Agent keys.
- **IBM Bob** — used to plan and implement the watsonx.ai routing and chat
  integrations, conduct security and code reviews, and derive architecture
  documentation from the working codebase.

## Where it goes next

- Swap CSV ingestion for a live AIS / TOS feed behind the existing `datasets.py` interface.
- Cache plans on a dataset fingerprint so repeated dashboard loads skip recomputation.
- Real crane allocation, rather than reporting the crane count a berth happens to have.
- Timezone-aware timestamps and a configurable planning horizon.
- Alternate-port capacity from a live source instead of a static catalogue.
- Extend the chat assistant with multi-plan comparison and shift handover note generation.
