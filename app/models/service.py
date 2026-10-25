"""Catalogue of services offered by the studio."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.formatting import format_money
from app.models.enums import ServiceCategory

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.order import Order


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str] = mapped_column(String(400), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    category: Mapped[ServiceCategory] = mapped_column(
        Enum(ServiceCategory, native_enum=False, length=32),
        index=True,
        default=ServiceCategory.SITES,
    )
    # `tags` is a JSON array of short strings, rendered as chips in the UI.
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    price_from: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    duration_days: Mapped[int] = mapped_column(Integer, default=14)
    icon: Mapped[str] = mapped_column(String(16), default="🚀")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    orders: Mapped[list[Order]] = relationship(back_populates="service")

    @property
    def category_label(self) -> str:
        return self.category.label

    @property
    def price_display(self) -> str:
        return format_money(self.price_from, prefix="от ")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Service id={self.id} slug={self.slug!r}>"
