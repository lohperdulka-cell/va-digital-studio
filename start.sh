#!/usr/bin/env sh
# Production entrypoint: apply migrations, then serve.
#
# Used by both the Docker image and Render's native runtime, so the two cannot
# drift apart.  Migrations run here rather than in a release phase because a
# single-instance deployment has nowhere else to put them.
set -e

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

# Worker count is deliberately 1 by default.  The WebSocket chat hub
# (app/services/chat.py) and the rate limiter (app/security/ratelimit.py) keep
# their state in process memory, so a second worker would give each half of a
# conversation its own view of the room and its own request counters.  Raise
# WEB_CONCURRENCY only after moving that state to Redis.
WORKERS="${WEB_CONCURRENCY:-1}"

echo "[start] applying database migrations"
alembic upgrade head

# Fill an empty catalogue and sync ADMIN_EMAILS on every boot.  This is what
# makes a card-free host (no Shell access) usable: the free tiers on Render and
# Back4App give you no way to run `python -m app.seed` by hand.  Failures here
# are logged but never block the server — a content problem must not take the
# site down.
echo "[start] bootstrapping content and admin rights"
python -m app.seed --bootstrap || echo "[start] WARNING: bootstrap failed, continuing"

echo "[start] serving on ${HOST}:${PORT} with ${WORKERS} worker(s)"

if command -v gunicorn >/dev/null 2>&1; then
    # UvicornWorker runs the ASGI app; gunicorn handles process supervision,
    # restarts and graceful reloads.  The timeout is generous because the OAuth
    # token exchange is a blocking outbound call.
    exec gunicorn app.main:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers "${WORKERS}" \
        --bind "${HOST}:${PORT}" \
        --timeout 120 \
        --graceful-timeout 30 \
        --access-logfile - \
        --error-logfile -
fi

echo "[start] gunicorn not found, falling back to uvicorn"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"
