# syntax=docker/dockerfile:1
# Multi-stage build for PortPulse.
#
# Stage 1 installs runtime dependencies into a virtualenv; stage 2 copies only
# that virtualenv and the package, so build tooling and dev dependencies never
# reach the runtime image.

# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies are copied first so this layer is cached until they change.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-deps .

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORTPULSE_HOST=0.0.0.0 \
    PORTPULSE_PORT=8000 \
    PORTPULSE_ENVIRONMENT=production \
    PORTPULSE_LOG_JSON=true

# Run as an unprivileged user.
RUN groupadd --system --gid 1001 portpulse \
    && useradd --system --uid 1001 --gid portpulse --create-home portpulse

COPY --from=builder --chown=root:root /opt/venv /opt/venv

WORKDIR /app
USER portpulse

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Uvicorn with proxy-header support; put a real reverse proxy in front in production.
CMD ["python", "-m", "uvicorn", "portpulse.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--no-server-header"]
