"""Framework-agnostic planning logic.

Nothing in this package imports FastAPI. Each module answers one operational
question:

* :mod:`portpulse.domain.prediction` — which windows will exceed capacity?
* :mod:`portpulse.domain.assignment` — which vessel goes to which berth?
* :mod:`portpulse.domain.routing`    — where should an unplaceable vessel go?
* :mod:`portpulse.domain.planner`    — combine the three into one plan.
"""

from __future__ import annotations

__all__ = ["assignment", "planner", "prediction", "routing"]
