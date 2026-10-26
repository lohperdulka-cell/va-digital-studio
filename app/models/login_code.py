"""One-time login codes for the e-mail and Telegram entry paths.

Only the hash of a code is stored, so a leaked database dump does not hand
anyone a working login.  A code is single-use: it is deleted as soon as it is
redeemed, and it dies after a small number of wrong guesses.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoginCode(Base):
    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Lower-case e-mail the code was sent to.  Always set; for Telegram the
    # bot still needs an address to attach the account to, so the code is
    # keyed by e-mail on every channel.
    email: Mapped[str] = mapped_column(String(320), index=True)

    # Which channel produced the code: "email" or "telegram".
    channel: Mapped[str] = mapped_column(String(16), default="email")

    # SHA-256 hex of the code.  Never store the code itself.
    code_hash: Mapped[str] = mapped_column(String(64))

    # Telegram chat id when channel == "telegram"; empty otherwise.
    telegram_id: Mapped[str] = mapped_column(String(64), default="")
    telegram_username: Mapped[str] = mapped_column(String(64), default="")

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_login_codes_email_channel", "email", "channel"),)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<LoginCode email={self.email!r} channel={self.channel!r}>"
