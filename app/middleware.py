"""Middleware: attach the current user to ``request.state`` and set headers."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.database import SessionLocal
from app.logging_config import get_logger
from app.security.sessions import user_from_request

logger = get_logger(__name__)


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

        if not request.url.path.startswith("/static/"):
            db = SessionLocal()
            try:
                user = user_from_request(request, db)
                if user is not None:
                    # Self-heal admin rights from ADMIN_EMAILS on every request.
                    # The JWT never carries the flag (it is read from the row),
                    # so an address added to ADMIN_EMAILS takes effect without a
                    # fresh login.  Only writes when the value actually changes.
                    if not user.is_admin and user.email in settings.admin_email_list:
                        user.is_admin = True
                        db.commit()
                        logger.info("Granted admin via ADMIN_EMAILS to %s", user.email)
                    # Detach: the row is read-only here and the session closes
                    # before the route's own session opens.
                    db.expunge(user)
                    request.state.user = user
                    request.state.is_admin = user.is_admin
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to resolve current user")
            finally:
                db.close()

        return await call_next(request)
