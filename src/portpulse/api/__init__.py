"""HTTP API layer.

``health_router`` is unversioned so orchestrators always have a stable probe URL.
Everything else lives behind ``/api/v1`` so the contract can evolve without
breaking existing clients.
"""

from __future__ import annotations

from fastapi import APIRouter

from portpulse.api import datasets as datasets_routes
from portpulse.api import health as health_routes
from portpulse.api import plan as plan_routes

API_V1_PREFIX = "/api/v1"

health_router = health_routes.router

api_v1_router = APIRouter(prefix=API_V1_PREFIX)
api_v1_router.include_router(plan_routes.router)
api_v1_router.include_router(datasets_routes.router)
api_v1_router.include_router(health_routes.router)

__all__ = ["API_V1_PREFIX", "api_v1_router", "health_router"]
