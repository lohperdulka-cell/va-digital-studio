"""Session cookie handling and the ``current_user`` dependency.

The session is a JWT stored in an httponly cookie.  There is no server-side
session store, so logout is performed by clearing the cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from app.config import settings
from app.database import get_db
from app.errors import ForbiddenError, NotAuthenticatedError
from app.logging_config import get_logger
from app.models import User
from app.security.tokens import create_session_token, decode_session_token

logger = get_logger(__name__)

SESSION_COOKIE_NAME = "va_session"
STATE_COOKIE_NAME = "va_oauth_state"
VERIFIER_COOKIE_NAME = "va_oauth_verifier"

_COOKIE_PATH = "/"


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
        expires=expires_at,
        max_age=settings.jwt_expire_days * 24 * 3600,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def issue_session(response: Response, user: User) -> None:
    """Mint a session token for ``user`` and attach it to the response."""
    token, expires_at = create_session_token(
        user_id=user.id, email=user.email, is_admin=user.is_admin
    )
    set_session_cookie(response, token, expires_at)


def set_handshake_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    """Short-lived httponly cookie used during the OAuth round-trip."""
    response.set_cookie(
        key=name,
        value=value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
        max_age=max_age,
    )


def clear_handshake_cookies(response: Response) -> None:
    for name in (STATE_COOKIE_NAME, VERIFIER_COOKIE_NAME):
        response.delete_cookie(key=name, path=_COOKIE_PATH, samesite="lax")


def user_from_request(request: HTTPConnection, db: Session) -> User | None:
    """Resolve the session cookie into a live, active user row.

    Accepts any ``HTTPConnection`` so the same check serves both HTTP requests
    and the WebSocket handshake.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    claims = decode_session_token(token)
    if claims is None:
        return None

    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        return None
    return user


def get_current_user_optional(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> User | None:
    """FastAPI dependency: the user or ``None`` — never raises."""
    user = user_from_request(request, db)
    # Middleware has usually populated this already; keep it in sync for routes.
    request.state.user = user
    return user


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    """FastAPI dependency: the user or a 401."""
    if user is None:
        raise NotAuthenticatedError()
    return user


def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """FastAPI dependency: an authenticated administrator or a 403."""
    if not user.is_admin:
        logger.warning("Admin access denied for user_id=%s", user.id)
        raise ForbiddenError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
AdminUser = Annotated[User, Depends(get_current_admin)]
DbSession = Annotated[Session, Depends(get_db)]


def utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "SESSION_COOKIE_NAME",
    "STATE_COOKIE_NAME",
    "AdminUser",
    "CurrentUser",
    "DbSession",
    "OptionalUser",
    "clear_handshake_cookies",
    "clear_session_cookie",
    "get_current_admin",
    "get_current_user",
    "get_current_user_optional",
    "issue_session",
    "set_handshake_cookie",
    "set_session_cookie",
    "user_from_request",
    "utcnow",
]
