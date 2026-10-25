# syntax=docker/dockerfile:1

# --- Build stage ----------------------------------------------------------
# Wheels are built here so the runtime image stays free of compilers.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# --- Runtime stage --------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000

# libpq is needed at runtime for the psycopg binary; curl backs the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY --chown=appuser:appuser . .

# Writable directories for logs and the SQLite fallback, owned by the runtime
# user so a mounted volume or a fresh container can both write here.
RUN mkdir -p /app/logs /app/data \
    && chown -R appuser:appuser /app/logs /app/data \
    && chmod +x /app/start.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1

# Migrations run on start so a fresh database is usable without manual steps.
CMD ["/app/start.sh"]
