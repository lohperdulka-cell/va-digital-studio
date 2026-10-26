"""Account provisioning and login bookkeeping."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models import User
from app.security.passwords import hash_password, verify_password
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
    e-mail second, so a pre-existing row (for example one created with
    email+password, or seeded from ``ADMIN_EMAILS``) is adopted rather than
    duplicated — signing in with Google links the two identities.
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

    _apply_admin_policy(db, user)

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


def _apply_admin_policy(db: Session, user: User) -> None:
    """Decide ``is_admin`` for ``user``.

    ``ADMIN_EMAILS`` is authoritative: an address on the list is an admin.
    When the list is empty, the *oldest* account owns the dashboard instead —
    a card-free host offers no Shell to run ``python -m app.cli make_admin`` in,
    so without this fallback nobody could ever reach ``/dashboard``.

    Only the oldest account can be promoted this way, and only while the site
    has no administrator at all, so a later visitor can neither take the flag
    nor lose it.
    """
    if user.email.lower() in settings.admin_email_list:
        if not user.is_admin:
            logger.info("Granting admin via ADMIN_EMAILS to %s", user.email)
        user.is_admin = True
        return

    if settings.admin_email_list or user.is_admin:
        return

    if _count_admins(db) or not _is_oldest_account(db, user):
        return

    logger.info("No ADMIN_EMAILS set: promoting %s as the owner account", user.email)
    user.is_admin = True


def _count_admins(db: Session) -> int:
    return (
        db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True)))
        or 0
    )


def _is_oldest_account(db: Session, user: User) -> bool:
    """True when ``user`` is the first account ever created."""
    if user.id is None:
        # Not flushed yet, so the table is empty exactly when this is the first
        # account; a pending row cannot be compared by id.
        return (db.scalar(select(func.count()).select_from(User)) or 0) == 0

    first_id = db.scalar(select(func.min(User.id)))
    return first_id == user.id


def apply_admin_policy(db: Session, user: User) -> None:
    """Public wrapper so middleware and routes share one policy."""
    _apply_admin_policy(db, user)


class EmailTakenError(Exception):
    """Raised when registration hits an address that already exists."""


class UsernameTakenError(Exception):
    """Raised when the chosen login name is already in use."""


def find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def find_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == normalize_username(username)))


def find_by_login(db: Session, identifier: str) -> User | None:
    """Resolve the sign-in field, which accepts either an e-mail or a login."""
    value = (identifier or "").strip()
    if "@" in value:
        return find_by_email(db, value)
    return find_by_username(db, value)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_username(username: str) -> str:
    """Lower-case the login so ``Ivan`` and ``ivan`` are the same account."""
    return (username or "").strip().lower()


def register_with_password(
    db: Session, *, email: str, password: str, name: str = "", username: str = ""
) -> User:
    """Create an email+password account.

    Raises :class:`EmailTakenError` or :class:`UsernameTakenError` when the
    address or login is already used; the caller decides whether to say so (an
    honest message here is more useful than a vague one, and the rate limiter
    blunts enumeration).
    """
    address = normalize_email(email)
    handle = normalize_username(username)
    existing = find_by_email(db, address)
    if existing is not None:
        raise EmailTakenError("Аккаунт с таким e-mail уже существует — войдите")
    if handle and find_by_username(db, handle) is not None:
        raise UsernameTakenError("Этот логин уже занят — выберите другой")

    user = User(
        email=address,
        username=handle or None,
        name=(name or "").strip(),
        password_hash=hash_password(password),
    )
    _apply_admin_policy(db, user)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTakenError("Аккаунт с таким e-mail уже существует — войдите") from exc

    db.refresh(user)
    logger.info("Registered email+password account: user_id=%s", user.id)
    return user


def authenticate_password(db: Session, *, login: str, password: str) -> User | None:
    """Return the user when the password is right, else ``None``.

    ``login`` is the e-mail address or the login name.  Deliberately returns the
    same result for "no such account" and "wrong password" so the response
    cannot be used to probe for addresses.
    """
    user = find_by_login(db, login)
    if user is None or not user.is_active:
        # Spend comparable time on a missing account so timing does not leak.
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        logger.info("Failed password login for %s", user.email)
        return None

    user.last_login_at = utcnow()
    _apply_admin_policy(db, user)
    db.commit()
    db.refresh(user)
    return user


def upsert_by_email_code(
    db: Session, *, email: str, name: str = "", telegram_id: str = "", telegram_username: str = ""
) -> tuple[User, bool]:
    """Create or fetch the account behind a verified e-mail code.

    Used by both the e-mail-code and Telegram paths: possession of the code is
    the proof, so an account is created on first success.
    """
    address = normalize_email(email)
    user = find_by_email(db, address)
    created = user is None
    if user is None:
        user = User(email=address, name=(name or "").strip())
        db.add(user)

    if telegram_id:
        user.telegram_id = telegram_id
    if telegram_username:
        user.telegram_username = telegram_username
    user.last_login_at = utcnow()
    _apply_admin_policy(db, user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = find_by_email(db, address)
        if user is None:  # pragma: no cover - only on a genuine race loss
            raise
        created = False

    db.refresh(user)
    logger.info(
        "Code login: user_id=%s email=%s telegram=%s created=%s",
        user.id,
        user.email,
        bool(telegram_id),
        created,
    )
    return user, created


# A real bcrypt hash of an unguessable random string.  Verifying against it
# keeps the "unknown account" path as slow as the "wrong password" path.
_DUMMY_HASH = "$2b$12$a5yzwzns9t2Wz1xqDj.1req4nKnjWZOFW5yo3EClzPcdSjOv2B5Fm"

