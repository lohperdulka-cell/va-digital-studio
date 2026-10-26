"""Portfolio cases: completed work shown on the site.

A case is intentionally decoupled from :class:`~app.models.service.Service`:
services describe what we sell, cases describe what we shipped.  The optional
``service_slug`` link lets a case point back at the offer it came from without
a foreign key, so deleting a service never orphans its portfolio entry.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    client: Mapped[str] = mapped_column(String(160), default="")
    summary: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")

    # A single headline number shown on the card, e.g. "заявок +40%".
    result_metric: Mapped[str] = mapped_column(String(160), default="")
    cover_emoji: Mapped[str] = mapped_column(String(8), default="🧩")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Free-form link to the live project, shown when present.
    external_url: Mapped[str] = mapped_column(String(500), default="")
    # Matches Service.slug when the case came from a catalog offer.
    service_slug: Mapped[str] = mapped_column(String(160), default="")

    is_published: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

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

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Case id={self.id} slug={self.slug!r}>"
