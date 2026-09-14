"""Console entry point: ``python -m portpulse`` or ``portpulse``."""

from __future__ import annotations

import uvicorn

from portpulse.config import get_settings
from portpulse.logging_setup import configure_logging


def main() -> None:
    """Start the development server using the configured host and port."""
    settings = get_settings().app
    configure_logging(settings.log_level, json_output=settings.log_json)
    uvicorn.run(
        "portpulse.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,  # logging is already configured above
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
