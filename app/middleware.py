"""Middleware: attach the current user to ``request.state`` and set headers."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.database import SessionLocal
from app.i18n import (
    LOCALE_COOKIE_NAME,
    LOCALE_QUERY_PARAM,
    normalize_locale,
    set_locale,
)
from app.logging_config import get_logger
from app.security.sessions import user_from_request
from app.services.accounts import apply_admin_policy

logger = get_logger(__name__)

#: A year, so the choice survives a browser restart.
LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def _resolve_locale(request: Request) -> tuple[str, bool]:
    """Pick the request locale; the flag says whether it came from ``?lang=``.

    Precedence: an explicit ``?lang=`` wins so a shared link opens in the
    language it names, then the visitor's cookie, then Russian.  Only the
    explicit parameter is worth persisting — a cookie is a stored preference,
    and a header guess should not silently become one.
    """
    from_query = normalize_locale(request.query_params.get(LOCALE_QUERY_PARAM))
    if from_query is not None:
        return set_locale(from_query), True

    from_cookie = normalize_locale(request.cookies.get(LOCALE_COOKIE_NAME))
    if from_cookie is not None:
        return set_locale(from_cookie), False

    return set_locale(None), False


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """Resolve the session cookie once per request.

    Templates and dependencies then read ``request.state.user`` instead of
    re-decoding the JWT.  Static files are skipped to keep the hot path cheap.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.user = None
        request.state.is_admin = False

        locale, persist = _resolve_locale(request)
        request.state.locale = locale

        if not request.url.path.startswith("/static/"):
            db = SessionLocal()
            try:
                user = user_from_request(request, db)
                if user is not None:
                    # Self-heal admin rights on every request, from
                    # ADMIN_EMAILS or from the no-ADMIN_EMAILS owner fallback.
                    # The JWT never carries the flag (it is read from the row),
                    # so this takes effect without a fresh login.  Only writes
                    # when the value actually changes.
                    if not user.is_admin:
                        apply_admin_policy(db, user)
                        if user.is_admin:
                            db.commit()
                    # Detach: the row is read-only here and the session closes
                    # before the route's own session opens.
                    db.expunge(user)
                    request.state.user = user
                    request.state.is_admin = user.is_admin
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to resolve current user")
            finally:
                db.close()

        response = await call_next(request)

        if persist:
            response.set_cookie(
                LOCALE_COOKIE_NAME,
                locale,
                max_age=LOCALE_COOKIE_MAX_AGE,
                httponly=False,
                samesite="lax",
                secure=request.url.scheme == "https",
            )

        return response
