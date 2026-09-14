# Solution Overview

## What we built

PortPulse ingests vessel arrival schedules and berth capacity data, forecasts which
upcoming windows are at risk of congestion, assigns vessels to berths by priority,
and — for any vessel that cannot be placed — recommends an alternate port with
AI-written reasoning. The result is a single 72-hour operations plan on a live
dashboard, exportable as CSV.

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

## Using the dashboard

- **Header metrics:** total incoming TEU, assigned and unassigned vessel counts, and
  the peak risk window.
- **72-hour congestion forecast:** one card per 24-hour window with the risk level
  and the capacity ratio behind it.
- **Berth assignment schedule:** searchable table of vessel, berth, cranes, arrival,
  estimated departure, queue wait, priority and the reason for the placement.
- **AI alternate routing:** one card per unassigned vessel with the rejection reason
  and ranked alternate ports.
- **Upload / Reset / Export:** swap in your own CSV, return to the sample dataset,
  or export the plan.

## Key design decisions

| Decision | Rationale |
|---|---|
| Greedy allocation, not a linear program | Fast, deterministic, and every decision is explainable to a supervisor. A solver optimises better but is far harder to trust or debug mid-shift. |
| Rolling 24-hour windows | Matches shift-by-shift planning rather than a single point-in-time snapshot. |
| AI applied only to the reroute explanation | The numeric work is deterministic and testable. The LLM is used where language is genuinely the deliverable, and its failure never blocks a plan. |
| Synthetic CSV data | No access to a live port scheduling system during the hackathon. The column contract is deliberately simple so a real feed can replace it. |
| Domain layer free of any web framework | The planning logic is unit-testable and reusable outside HTTP; the API layer only translates errors into status codes. |

## IBM technologies

- **IBM watsonx.ai** — `ibm/granite-3-8b-instruct` via the REST text-generation API,
  used to explain vessel rejections and justify alternate-port recommendations.
  Access is wrapped in a client with IAM token caching, jittered retries and an
  authentication circuit breaker.
- **IBM Bob** — used to plan and implement the watsonx.ai routing integration and to
  derive the architecture documentation from the working codebase.

## Where it goes next

- Swap CSV ingestion for a live AIS / TOS feed behind the existing `datasets.py` interface.
- Cache plans on a dataset fingerprint so repeated dashboard loads skip recomputation.
- Real crane allocation, rather than reporting the crane count a berth happens to have.
- Timezone-aware timestamps and a configurable planning horizon.
- Alternate-port capacity from a live source instead of a static catalogue.
