"""Account provisioning and login bookkeeping."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models import User
from app.security.sessions import utcnow

logger = get_logger(__name__)


class OAuthProfileError(Exception):
    """Raised when Google returns a payload we cannot trust or use."""


def profile_from_id_token(claims: dict[str, Any]) -> dict[str, Any]:
    """Normalise an ID-token payload into the fields we persist.

    Google's OIDC payload is only accepted when it carries the identifiers the
    rest of the application depends on.
    """
    subject = claims.get("sub")
    email = (claims.get("email") or "").strip().lower()

    if not subject or not email:
        raise OAuthProfileError("Google did not return a subject or email address")
    if claims.get("email_verified") is False:
        raise OAuthProfileError("Google account email is not verified")

    return {
        "google_id": str(subject),
        "email": email,
        "name": (claims.get("name") or "").strip(),
        "avatar_url": claims.get("picture") or None,
    }


def upsert_user(db: Session, profile: dict[str, Any]) -> tuple[User, bool]:
    """Create or refresh the account for a Google profile.

    Returns ``(user, created)``.  Matching is done on ``google_id`` first and
    e-mail second, so a pre-existing row (for example one seeded from
    ``ADMIN_EMAILS``) is adopted rather than duplicated.
    """
    user = db.scalar(select(User).where(User.google_id == profile["google_id"]))
    if user is None:
        user = db.scalar(select(User).where(User.email == profile["email"]))

    created = user is None
    if user is None:
        user = User(
            google_id=profile["google_id"],
            email=profile["email"],
            name=profile["name"],
            avatar_url=profile["avatar_url"],
        )
        db.add(user)

    # Refresh fields Google owns on every login.
    user.google_id = profile["google_id"]
    user.email = profile["email"]
    if profile["name"]:
        user.name = profile["name"]
    if profile["avatar_url"]:
        user.avatar_url = profile["avatar_url"]
    user.last_login_at = utcnow()

    # ADMIN_EMAILS is authoritative on every login (requirement 4.1).
    if profile["email"] in settings.admin_email_list:
        if not user.is_admin:
            logger.info("Granting admin via ADMIN_EMAILS to %s", profile["email"])
        user.is_admin = True

    try:
        db.commit()
    except IntegrityError:
        # Two concurrent first logins for the same account: keep the winner.
        db.rollback()
        user = db.scalar(select(User).where(User.email == profile["email"]))
        if user is None:  # pragma: no cover - only on a genuine race loss
            raise
        created = False

    db.refresh(user)
    logger.info(
        "Google login: user_id=%s email=%s admin=%s created=%s",
        user.id,
        user.email,
        user.is_admin,
        created,
    )
    return user, created
