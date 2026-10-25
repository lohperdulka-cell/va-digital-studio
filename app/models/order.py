"""Client orders and their lifecycle."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.formatting import format_money
from app.models.enums import OrderStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.chat import ChatMessage
    from app.models.service import Service
    from app.models.user import User


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), index=True, default=None
    )

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=32),
        default=OrderStatus.DRAFT,
        index=True,
    )
    # Filled in by an administrator once the scope is agreed.
    price_final: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="orders")
    service: Mapped[Service | None] = relationship(back_populates="orders")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    @property
    def service_title(self) -> str:
        return self.service.title if self.service else "Индивидуальный проект"

    @property
    def price_display(self) -> str:
        return format_money(self.price_final)

    def unread_for(self, *, is_admin: bool) -> int:
        """Count messages the given side has not read yet."""
        return sum(
            1
            for message in self.messages
            if not message.is_read and message.from_admin != is_admin
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Order id={self.id} status={self.status.value}>"
