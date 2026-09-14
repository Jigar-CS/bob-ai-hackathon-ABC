"""API key authentication for state-changing endpoints.

Authentication is opt-in: set ``PORTPULSE_API_KEY`` to require an ``X-API-Key``
header on write endpoints. When the variable is unset the endpoints stay open so
the local dashboard works out of the box — the app logs a warning at startup and
refuses to boot in that state when ``PORTPULSE_ENVIRONMENT=production``.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from portpulse.config import Settings, get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def require_api_key(
    provided_key: str | None = Depends(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency guarding write endpoints.

    Raises:
        HTTPException: 401 when a key is configured and the header is missing or wrong.
    """
    expected = settings.app.api_key
    if expected is None:
        return

    if not provided_key or not hmac.compare_digest(provided_key, expected):
        logger.warning("Rejected request with missing or invalid %s header", API_KEY_HEADER_NAME)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": API_KEY_HEADER_NAME},
        )
