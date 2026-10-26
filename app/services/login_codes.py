"""Issue and redeem one-time login codes (e-mail and Telegram).

Security properties:
  * the code is random from ``secrets``, never derived from the address;
  * only its SHA-256 hash is stored, so a database dump is not a login;
  * it expires (default 10 minutes) and is burned after a few wrong guesses;
  * redeeming deletes every outstanding code for that address, so an old
    e-mail in the inbox cannot be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import get_logger
from app.models import LoginCode
from app.security.sessions import utcnow

logger = get_logger(__name__)

CHANNEL_EMAIL = "email"
CHANNEL_TELEGRAM = "telegram"

_CODE_DIGITS = 6


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _purge_expired(db: Session) -> None:
    """Drop every code whose time is up, regardless of owner."""
    db.execute(delete(LoginCode).where(LoginCode.expires_at < utcnow()))


def issue_code(
    db: Session,
    *,
    email: str,
    channel: str = CHANNEL_EMAIL,
    telegram_id: str = "",
    telegram_username: str = "",
) -> str:
    """Create a fresh code for ``email`` and return the plaintext code.

    Any code still outstanding for the same address and channel is removed
    first, so requesting a new code invalidates the previous one.
    """
    address = normalize_email(email)
    _purge_expired(db)
    db.execute(
        delete(LoginCode).where(
            LoginCode.email == address, LoginCode.channel == channel
        )
    )

    code = "".join(secrets.choice("0123456789") for _ in range(_CODE_DIGITS))
    db.add(
        LoginCode(
            email=address,
            channel=channel,
            code_hash=_hash_code(code),
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            expires_at=utcnow() + timedelta(seconds=settings.login_code_ttl_seconds),
        )
    )
    db.commit()
    logger.info("Issued %s login code for %s", channel, address)
    return code


class CodeError(Exception):
    """Raised when a submitted code cannot be redeemed."""


def redeem_code(
    db: Session, *, email: str, code: str, channel: str | None = None
) -> LoginCode:
    """Validate ``code`` for ``email`` and consume it.

    Raises :class:`CodeError` with a user-facing message on any failure.
    """
    address = normalize_email(email)
    submitted = (code or "").strip()
    if not submitted:
        raise CodeError("Введите код из письма")

    _purge_expired(db)

    query = select(LoginCode).where(LoginCode.email == address)
    if channel:
        query = query.where(LoginCode.channel == channel)
    candidates = list(db.scalars(query.order_by(LoginCode.created_at.desc())))

    if not candidates:
        raise CodeError("Код не найден или уже использован. Запросите новый.")

    record = candidates[0]

    if record.attempts >= settings.login_code_max_attempts:
        db.delete(record)
        db.commit()
        logger.warning("Login code for %s burned after too many attempts", address)
        raise CodeError("Слишком много неверных попыток. Запросите новый код.")

    if not hmac.compare_digest(record.code_hash, _hash_code(submitted)):
        record.attempts += 1
        db.commit()
        remaining = settings.login_code_max_attempts - record.attempts
        if remaining <= 0:
            raise CodeError("Слишком много неверных попыток. Запросите новый код.")
        raise CodeError(f"Неверный код. Осталось попыток: {remaining}")

    # Success: consume every code for this address so nothing can be replayed.
    db.execute(delete(LoginCode).where(LoginCode.email == address))
    db.commit()
    logger.info("Redeemed %s login code for %s", record.channel, address)
    return record
