"""JWT issuing and verification.

Two token kinds share one signing key but are separated by the ``typ`` claim so
a short-lived OAuth handshake token can never be replayed as a session token.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.config import settings

SESSION_TYP: Final = "session"
OAUTH_STATE_TYP: Final = "oauth_state"

STATE_TTL_SECONDS: Final = 600  # 10 minutes is plenty for a login round-trip

_REQUIRED_CLAIMS: Final = ["exp", "iat", "iss", "sub"]


def _now() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": _REQUIRED_CLAIMS},
        )
    except (ExpiredSignatureError, InvalidTokenError):
        return None


# --- Session tokens --------------------------------------------------------


def create_session_token(*, user_id: int, email: str, is_admin: bool) -> tuple[str, datetime]:
    """Return ``(token, expires_at)`` for the browser session cookie."""
    issued_at = _now()
    expires_at = issued_at + timedelta(days=settings.jwt_expire_days)
    token = _encode(
        {
            "sub": str(user_id),
            "email": email,
            "adm": bool(is_admin),
            "typ": SESSION_TYP,
            "iss": settings.jwt_issuer,
            "iat": issued_at,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(16),
        }
    )
    return token, expires_at


def decode_session_token(token: str) -> dict[str, Any] | None:
    """Validate signature, issuer and expiry; return claims or ``None``."""
    claims = _decode(token)
    if claims is None or claims.get("typ") != SESSION_TYP:
        return None
    try:
        int(claims["sub"])
    except (KeyError, TypeError, ValueError):
        return None
    return claims


# --- OAuth state tokens ----------------------------------------------------


def create_state_token(next_path: str) -> tuple[str, str]:
    """Return ``(state, nonce)``; both travel through Google and back."""
    nonce = secrets.token_urlsafe(24)
    state = _encode(
        {
            "sub": nonce,
            "nonce": nonce,
            "nxt": next_path,
            "typ": OAUTH_STATE_TYP,
            "iss": settings.jwt_issuer,
            "iat": _now(),
            "exp": _now() + timedelta(seconds=STATE_TTL_SECONDS),
            "jti": secrets.token_urlsafe(16),
        }
    )
    return state, nonce


def decode_state_token(state: str) -> dict[str, Any] | None:
    claims = _decode(state)
    if claims is None or claims.get("typ") != OAUTH_STATE_TYP:
        return None
    return claims


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


# --- PKCE helpers ----------------------------------------------------------


def generate_code_verifier() -> str:
    """RFC 7636 verifier: 43-128 characters from the unreserved set."""
    return secrets.token_urlsafe(64)


def code_challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --- Redirect safety -------------------------------------------------------


def safe_next_path(value: str | None, default: str = "/profile") -> str:
    """Only allow same-site relative paths, never protocol-relative or absolute."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    if "\\" in value or "\n" in value or "\r" in value:
        return default
    return value
