"""HTTP middleware: request correlation IDs, security headers, and rate limiting."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from typing import ClassVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# ── Security & Rate Limit settings ───────────────────────────────────────────
_SENSITIVE_PATHS: set[str] = {
    "/api/v1/chat",
    "/api/v1/uploads/vessels",
    "/api/v1/uploads/berths",
    "/api/v1/plan/custom",
}
_MAX_REQUESTS_PER_MINUTE = 30
_WINDOW_SECONDS = 60.0


class _RateLimiterState:
    def __init__(self) -> None:
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, ip: str, now: float) -> bool:
        timestamps = self.requests[ip]
        # Purge timestamps outside the window
        cutoff = now - _WINDOW_SECONDS
        self.requests[ip] = [t for t in timestamps if t > cutoff]
        if len(self.requests[ip]) >= _MAX_REQUESTS_PER_MINUTE:
            return True
        self.requests[ip].append(now)
        return False

    def clear(self) -> None:
        self.requests.clear()


_rate_limiter = _RateLimiterState()


def reset_rate_limiter() -> None:
    """Clear rate limiter state for tests."""
    _rate_limiter.clear()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request/response and log the outcome.

    An inbound ``X-Request-ID`` is honoured so the ID can be traced across a
    reverse proxy or a calling service; otherwise a new one is generated.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "%s %s failed after %.1fms",
                request.method,
                request.url.path,
                elapsed_ms,
                extra={"request_id": request_id},
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "%s %s -> %d in %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"request_id": request_id},
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers into all outgoing HTTP responses."""

    DEFAULT_HEADERS: ClassVar[dict[str, str]] = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https: http:; "
            "style-src 'self' 'unsafe-inline' https: http:; "
            "font-src 'self' https: http: data:; "
            "img-src 'self' data: blob: https: http:; "
            "connect-src 'self' https: http:;"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
        "X-Frame-Options": "DENY",
    }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in self.DEFAULT_HEADERS.items():
            if header not in response.headers:
                response.headers[header] = value

        is_https = (
            request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        )
        if is_https and "Strict-Transport-Security" not in response.headers:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter guarding high-cost API endpoints."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path in _SENSITIVE_PATHS and request.method == "POST":
            client_ip = request.client.host if request.client else "127.0.0.1"
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()

            now = time.monotonic()
            if _rate_limiter.is_rate_limited(client_ip, now):
                logger.warning("Rate limit exceeded for IP %s on %s", client_ip, path)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please wait before retrying."},
                    headers={"Retry-After": "60"},
                )

        return await call_next(request)
