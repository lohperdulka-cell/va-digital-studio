"""User accounts (Google OAuth) and balance."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.chat import ChatMessage
    from app.models.news import NewsLike
    from app.models.order import Order
    from app.models.review import Review
    from app.models.support import SupportTicket


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Google's `sub` claim.  Nullable because an account may be created with
    # email+password or Telegram and never linked to Google.
    google_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=None
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Public handle chosen at registration, stored lower-cased so uniqueness is
    # case-insensitive.  NULL for accounts that never picked one (Google-only or
    # Telegram-only); such an account signs in with its e-mail.
    username: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, default=None
    )
    name: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str | None] = mapped_column(String(1024), default=None)

    # --- Email + password login -------------------------------------------
    # NULL means "this account has no password" (Google-only or Telegram-only).
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    # --- Telegram login ----------------------------------------------------
    telegram_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=None
    )
    telegram_username: Mapped[str | None] = mapped_column(String(64), default=None)

    balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    orders: Mapped[list[Order]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    likes: Mapped[list[NewsLike]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="sender", cascade="all, delete-orphan"
    )
    support_tickets: Mapped[list[SupportTicket]] = relationship(
        back_populates="user"
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [part for part in self.name.split() if part]
        if not parts:
            return (self.email[:1] or "?").upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][:1] + parts[1][:1]).upper()

    @property
    def display_name(self) -> str:
        return self.name or self.username or self.email.split("@")[0]

    @property
    def handle(self) -> str:
        """The ``@name`` shown in the UI; falls back to the e-mail local part."""
        return self.username or self.email.split("@")[0]

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def login_methods(self) -> list[str]:
        """Human-readable list of the ways this account can be entered."""
        methods = []
        if self.password_hash:
            methods.append("email")
        if self.google_id:
            methods.append("google")
        if self.telegram_id:
            methods.append("telegram")
        return methods

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} email={self.email!r} admin={self.is_admin}>"
