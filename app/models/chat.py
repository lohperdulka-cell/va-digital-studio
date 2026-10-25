"""Real-time chat messages attached to an order."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MessageKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.order import Order
    from app.models.user import User


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_order_created", "order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    sender_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )

    # Stored already sanitised (see app/security/sanitize.py).
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[MessageKind] = mapped_column(
        Enum(MessageKind, native_enum=False, length=16),
        default=MessageKind.CLIENT,
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    order: Mapped[Order] = relationship(back_populates="messages")
    sender: Mapped[User | None] = relationship(back_populates="chat_messages")

    @property
    def from_admin(self) -> bool:
        """True when the message came from studio staff."""
        return self.kind is not MessageKind.CLIENT

    @property
    def sender_name(self) -> str:
        if self.kind is MessageKind.SYSTEM:
            return "Система"
        if self.sender is None:
            return "Менеджер"
        return self.sender.display_name

    @property
    def sender_avatar(self) -> str | None:
        return self.sender.avatar_url if self.sender else None

    def to_payload(self) -> dict[str, object]:
        """Wire format shared by the WebSocket broadcast and the REST history."""
        return {
            "id": self.id,
            "order_id": self.order_id,
            "text": self.text,
            "kind": self.kind.value,
            "from_admin": self.from_admin,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "sender_avatar": self.sender_avatar,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_at_label": self.created_at.strftime("%d.%m.%Y %H:%M")
            if self.created_at
            else "",
        }


class ChatPresence:
    """In-memory registry of who is currently connected to an order chat.

    Deliberately process-local: a single Uvicorn worker is the supported
    deployment (see README).  Swap for Redis pub/sub to scale horizontally.
    """

    def __init__(self) -> None:
        self._rooms: dict[int, set[tuple[int, bool]]] = {}

    def join(self, order_id: int, user_id: int, is_admin: bool) -> None:
        self._rooms.setdefault(order_id, set()).add((user_id, is_admin))

    def leave(self, order_id: int, user_id: int, is_admin: bool) -> None:
        room = self._rooms.get(order_id)
        if not room:
            return
        room.discard((user_id, is_admin))
        if not room:
            self._rooms.pop(order_id, None)

    def admins_online(self, order_id: int) -> bool:
        return any(is_admin for _, is_admin in self._rooms.get(order_id, ()))

    def clients_online(self, order_id: int) -> bool:
        return any(not is_admin for _, is_admin in self._rooms.get(order_id, ()))


presence = ChatPresence()
