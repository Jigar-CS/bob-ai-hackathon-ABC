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


@router.get(
    "/db-status",
    summary="Check MySQL database connection status",
)
def db_status() -> dict[str, bool]:
    """Report MySQL database connection status."""
    from portpulse.db import check_connection as check_db_connection

    return {"database_connected": check_db_connection()}


@router.get(
    "/weather-status",
    summary="Check real-time weather API reachability and port configuration",
)
def weather_status(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Report weather API reachability and current port coordinate configuration.

    Performs a lightweight probe against the Open-Meteo API.
    Always returns 200 — ``weather_api_reachable`` is false when the API is
    unreachable (vessels will be scheduled with unadjusted ETAs).
    """
    import requests

    reachable = False
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={  # type: ignore[arg-type]
                "latitude": settings.app.port_lat,
                "longitude": settings.app.port_lon,
                "hourly": "wind_speed_10m",
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=settings.app.weather_api_timeout_seconds,
        )
        reachable = resp.status_code == 200
    except Exception:
        pass

    return {
        "weather_enabled": settings.app.weather_enabled,
        "weather_api_reachable": reachable,
        "port_lat": settings.app.port_lat,
        "port_lon": settings.app.port_lon,
    }
