"""FastAPI application factory.

Built as a factory rather than a module-level singleton so tests can construct
isolated apps with different settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from portpulse import __version__
from portpulse.api import api_v1_router, health_router
from portpulse.config import STATIC_DIR, Settings, get_settings
from portpulse.datasets import datasets_available
from portpulse.errors import (
    ConfigurationError,
    CsvValidationError,
    DataFileError,
    PlanningError,
)
from portpulse.logging_setup import configure_logging
from portpulse.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from portpulse.security import API_KEY_HEADER_NAME

logger = logging.getLogger(__name__)

DESCRIPTION = f"""
PortPulse forecasts container-port congestion over a 72-hour horizon, allocates
vessels to berths by priority, and uses IBM watsonx.ai to explain where vessels
that cannot be berthed should go instead.

* `GET /health` — liveness and readiness
* `GET /api/v1/plan` — the full operations plan
* `POST /api/v1/uploads/vessels` and `/api/v1/uploads/berths` — plan from your own CSV
* `GET /api/v1/plan/export.csv` — spreadsheet-ready export

Write endpoints require the `{API_KEY_HEADER_NAME}` header when `PORTPULSE_API_KEY` is set.
"""


def _verify_startup_configuration(settings: Settings) -> None:
    """Fail fast on configurations that are unsafe or cannot possibly work."""
    app_settings = settings.app

    if not STATIC_DIR.is_dir():
        raise ConfigurationError(
            f"Dashboard assets are missing from {STATIC_DIR}. The package is incomplete."
        )

    if app_settings.is_production:
        if app_settings.api_key is None:
            raise ConfigurationError(
                "PORTPULSE_API_KEY must be set when PORTPULSE_ENVIRONMENT=production: "
                "write endpoints would otherwise be unauthenticated."
            )
        if "*" in app_settings.cors_origins:
            raise ConfigurationError(
                "Wildcard CORS origins are not allowed in production. "
                "Set PORTPULSE_CORS_ALLOW_ORIGINS to an explicit list."
            )
    elif app_settings.api_key is None:
        logger.warning(
            "PORTPULSE_API_KEY is not set — upload and custom-plan endpoints are "
            "unauthenticated. Acceptable for local use; set it before exposing the service."
        )

    if not datasets_available(settings):
        logger.warning(
            "Default datasets were not found in %s. /api/v1/plan will return 503 until they "
            "exist — run: python scripts/generate_sample_data.py",
            app_settings.data_dir,
        )

    if settings.watsonx.enabled:
        logger.info("watsonx.ai configured with model %s", settings.watsonx.model_id)
    else:
        logger.info(
            "watsonx.ai credentials not configured — routing recommendations will use "
            "template text. Set WATSONX_API_KEY and WATSONX_PROJECT_ID to enable AI reasoning."
        )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    _verify_startup_configuration(settings)
    logger.info("PortPulse %s starting in %s mode", __version__, settings.app.environment)
    yield
    logger.info("PortPulse shutting down")


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConfigurationError)
    async def _handle_config_error(request: Request, exc: ConfigurationError) -> JSONResponse:
        logger.error("Configuration error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "A service configuration error occurred."},
        )

    @app.exception_handler(DataFileError)
    async def _handle_data_file_error(request: Request, exc: DataFileError) -> JSONResponse:
        logger.error("Dataset unavailable for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    f"{exc} Generate the sample datasets with "
                    "'python scripts/generate_sample_data.py'."
                )
            },
        )

    @app.exception_handler(CsvValidationError)
    async def _handle_csv_error(request: Request, exc: CsvValidationError) -> JSONResponse:
        logger.info("Rejected CSV on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(PlanningError)
    async def _handle_planning_error(request: Request, exc: PlanningError) -> JSONResponse:
        logger.info("Could not plan for %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)}
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Unhandled error on %s %s",
            request.method,
            request.url.path,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal error occurred."
                + (f" Reference: {request_id}" if request_id else "")
            },
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured PortPulse application."""
    settings = settings or get_settings()
    configure_logging(settings.app.log_level, json_output=settings.app.log_json)

    app = FastAPI(
        title="PortPulse",
        summary="Port congestion prediction and 72-hour berth operations planning.",
        description=DESCRIPTION,
        version=__version__,
        lifespan=_lifespan,
        docs_url=None if settings.app.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.app.is_production else "/api/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", API_KEY_HEADER_NAME],
    )

    _register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router)

    # The dashboard is a catch-all, so it must be mounted after every API route.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

    return app
