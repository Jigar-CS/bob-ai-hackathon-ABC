"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from portpulse import __version__
from portpulse.config import Settings, get_settings
from portpulse.datasets import datasets_available
from portpulse.schemas import HealthResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and readiness probe",
)
def health(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Report service health.

    Returns 200 when the default datasets are readable and 503 when they are not,
    so a container orchestrator can act on it. The service is still considered
    healthy without watsonx.ai credentials because routing degrades gracefully.
    """
    datasets_ok = datasets_available(settings)
    if not datasets_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="healthy" if datasets_ok else "degraded",
        service="portpulse",
        version=__version__,
        environment=settings.app.environment,
        watsonx_configured=settings.watsonx.enabled,
        datasets_available=datasets_ok,
    )
