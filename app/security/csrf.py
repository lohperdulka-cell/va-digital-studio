"""CSRF protection: double-submit cookie.

Two cooperating pieces:

* :class:`CsrfCookieMiddleware` guarantees every visitor holds a random
  ``va_csrf`` cookie (httponly, so page scripts cannot read it) and exposes the
  value as ``request.state.csrf_token`` for template rendering.
* :func:`require_csrf` is a dependency attached at router level.  On unsafe
  methods it compares the submitted token — an ``X-CSRF-Token`` header for
  fetch() calls, or a ``csrf_token`` form field for plain HTML forms — against
  the cookie in constant time.

The token is never rotated per request: a stable value keeps multiple tabs
working, and the cookie is only readable by the server.
"""

from __future__ import annotations

import secrets
from typing import Final

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import settings
from app.errors import AppError
from app.logging_config import get_logger
from app.security.tokens import constant_time_equals

CSRF_COOKIE_NAME: Final = "va_csrf"
CSRF_FIELD_NAME: Final = "csrf_token"
CSRF_HEADER_NAME: Final = "X-CSRF-Token"

SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# A day is long enough for a browsing session and short enough to limit exposure.
_TOKEN_MAX_AGE: Final = 24 * 3600

logger = get_logger(__name__)


class CsrfError(AppError):
    status_code = 403
    title = "Проверка CSRF не пройдена"
    detail = "Обновите страницу и попробуйте ещё раз"


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_token_for(request: Request) -> str:
    """The token to embed in forms and the ``<meta>`` tag."""
    return getattr(request.state, "csrf_token", "") or ""


class CsrfCookieMiddleware(BaseHTTPMiddleware):
    """Issue the CSRF cookie and publish the token on ``request.state``.

    Deliberately does not read the request body, so it composes safely with
    ``BaseHTTPMiddleware``'s streaming receive channel.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = request.cookies.get(CSRF_COOKIE_NAME) or ""
        issued = not token
        if issued:
            token = generate_token()
        request.state.csrf_token = token

        response = await call_next(request)

        if issued:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=token,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="lax",
                path="/",
                max_age=_TOKEN_MAX_AGE,
            )
        return response


async def require_csrf(request: Request) -> None:
    """Validate the CSRF token on unsafe methods; no-op for safe ones."""
    if request.method in SAFE_METHODS:
        return

    cookie = request.cookies.get(CSRF_COOKIE_NAME) or ""
    submitted = request.headers.get(CSRF_HEADER_NAME) or ""

    if not submitted:
        # Reading the form here is safe: Starlette caches the parse, so the
        # route handler re-reads the same object rather than the body stream.
        form = await request.form()
        submitted = str(form.get(CSRF_FIELD_NAME) or "")

    if not cookie or not submitted or not constant_time_equals(cookie, submitted):
        logger.warning(
            "CSRF rejection: %s %s (cookie=%s, submitted=%s)",
            request.method,
            request.url.path,
            bool(cookie),
            bool(submitted),
        )
        raise CsrfError()
