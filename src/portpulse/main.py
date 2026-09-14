"""ASGI entry point.

Run with::

    uvicorn portpulse.main:app --reload
"""

from __future__ import annotations

from portpulse.app import create_app

app = create_app()

__all__ = ["app"]
