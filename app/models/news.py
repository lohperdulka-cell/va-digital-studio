"""Studio news feed and per-user likes."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    preview: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    cover_emoji: Mapped[str] = mapped_column(String(8), default="📰")

    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    likes: Mapped[list[NewsLike]] = relationship(
        back_populates="news", cascade="all, delete-orphan"
    )

    @property
    def likes_count(self) -> int:
        return len(self.likes)

    def liked_by(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        return any(like.user_id == user_id for like in self.likes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<News id={self.id} slug={self.slug!r}>"


class NewsLike(Base):
    """One row per (user, news) pair — the unique constraint enforces it in the DB."""

    __tablename__ = "news_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "news_id", name="uq_news_likes_user_news"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    news_id: Mapped[int] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="likes")
    news: Mapped[News] = relationship(back_populates="likes")
