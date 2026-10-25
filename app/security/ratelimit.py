"""Per-IP rate limiting for the endpoints that cost something.

A fixed-window counter is enough here: the goal is to blunt brute force and
form spam on a handful of paths, not to shape traffic precisely.  State lives
in process memory, which matches the single-worker deployment the app already
assumes (see ``app.models.chat`` for the same trade-off).

The HTTP middleware below covers the form and auth endpoints; WebSocket frames
bypass it entirely, so ``app.routes.chat`` keeps its own limiter keyed by user.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# Path prefixes (and exact paths) that are rate limited.
GUARDED_PREFIXES: tuple[str, ...] = (
    "/auth/",
    "/support",
    "/contact",
)
GUARDED_EXACT: frozenset[str] = frozenset()


@dataclass
class _Window:
    count: int
    reset_at: float


@dataclass
class RateLimiter:
    """Fixed-window counter keyed by client IP."""

    limit: int
    window_seconds: int
    _buckets: dict[str, _Window] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str) -> tuple[bool, int, float]:
        """Register a hit; return ``(allowed, remaining, retry_after)``."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or bucket.reset_at <= now:
                bucket = _Window(count=0, reset_at=now + self.window_seconds)
                self._buckets[key] = bucket
            bucket.count += 1
            remaining = max(0, self.limit - bucket.count)
            allowed = bucket.count <= self.limit
            retry_after = max(0.0, bucket.reset_at - now)
            if len(self._buckets) > 10_000:  # opportunistic cleanup
                self._prune(now)
            return allowed, remaining, retry_after

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._buckets.items() if v.reset_at <= now]:
            del self._buckets[key]


limiter = RateLimiter(
    limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


def _is_guarded(path: str) -> bool:
    return path in GUARDED_EXACT or path.startswith(GUARDED_PREFIXES)


def _client_ip(request: Request) -> str:
    """Best-effort client identity behind a proxy.

    ``X-Forwarded-For`` is only trusted for the left-most hop; a deployment
    that terminates TLS in front of the app should set it consistently.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Return 429 with ``Retry-After`` once a guarded path exceeds its budget."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.rate_limit_enabled or not _is_guarded(request.url.path):
            return await call_next(request)

        allowed, remaining, retry_after = limiter.check(_client_ip(request))
        if not allowed:
            logger.warning(
                "Rate limit exceeded: ip=%s path=%s",
                _client_ip(request),
                request.url.path,
            )
            return JSONResponse(
                {"detail": "Слишком много запросов. Попробуйте позже."},
                status_code=429,
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Limit": str(limiter.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
