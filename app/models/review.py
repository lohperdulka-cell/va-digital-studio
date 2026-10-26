"""Client reviews, published after administrator approval.

Anyone may submit one; nothing appears on the site until an admin approves it.
That keeps spam and abuse off the public page without an external moderation
service.  A review may be linked to a registered user, but the author name is
stored on the row so the review survives account deletion.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User

MIN_RATING = 1
MAX_RATING = 5


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint(
            f"rating >= {MIN_RATING} AND rating <= {MAX_RATING}",
            name="ck_reviews_rating_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )

    author_name: Mapped[str] = mapped_column(String(120))
    author_role: Mapped[str] = mapped_column(String(160), default="")
    rating: Mapped[int] = mapped_column(Integer, default=MAX_RATING, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")

    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User | None] = relationship(back_populates="reviews")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Review id={self.id} rating={self.rating} approved={self.is_approved}>"
