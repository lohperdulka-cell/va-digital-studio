"""Order chat: history, persistence and the live connection hub.

The hub is process-local.  A single Uvicorn worker is the supported
deployment; scaling horizontally would mean swapping the in-process fan-out
for Redis pub/sub (see README).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.logging_config import get_logger
from app.models import ChatMessage, Order
from app.models.chat import presence
from app.models.enums import MessageKind
from app.schemas.forms import CHAT_MESSAGE_MAX
from app.security.sanitize import clean_plain_text

logger = get_logger(__name__)

#: Name shown to a client in place of an individual administrator.  A studio
#: identity is friendlier than an arbitrary staff member's name, and it stays
#: stable when the team changes.
SUPPORT_NAME = "Поддержка VA Digital"
SUPPORT_INITIALS = "VA"


# --- Persistence -----------------------------------------------------------


def load_history(db: Session, order_id: int) -> list[ChatMessage]:
    """Every message in the order, oldest first, senders eagerly loaded."""
    statement = (
        select(ChatMessage)
        .where(ChatMessage.order_id == order_id)
        .options(selectinload(ChatMessage.sender))
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    return list(db.scalars(statement))


def save_message(
    db: Session,
    *,
    order_id: int,
    sender_id: int | None,
    text: str,
    kind: MessageKind,
) -> dict[str, Any]:
    """Persist one chat message and return its wire payload.

    ``text`` is sanitised before it is stored.  The payload is built while the
    session is still open so the detached ORM object is never touched later.
    """
    message = ChatMessage(
        order_id=order_id,
        sender_id=sender_id,
        kind=kind,
        text=clean_plain_text(text, max_length=CHAT_MESSAGE_MAX),
        # Unread for the recipient until their side reads the room.  The
        # author's own side never counts it (see Order.unread_for), so there
        # is nothing to pre-mark here.
        is_read=False,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    # Touch the order so "updated_at" reflects chat activity in dashboards.
    db.execute(
        update(Order).where(Order.id == order_id).values(updated_at=message.created_at)
    )
    db.commit()
    db.refresh(message)
    return message.to_payload()


def mark_read(db: Session, *, order_id: int, is_admin: bool) -> int:
    """Mark the other side's messages as read. Returns rows affected."""
    # A client reading a chat marks staff messages, and vice versa.
    other_side = (
        ChatMessage.kind.in_([MessageKind.STAFF, MessageKind.SYSTEM])
        if not is_admin
        else ChatMessage.kind == MessageKind.CLIENT
    )
    result = db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.order_id == order_id,
            ChatMessage.is_read.is_(False),
            other_side,
        )
        .values(is_read=True)
    )
    db.commit()
    return int(result.rowcount or 0)


def can_access(order: Order, *, user_id: int, is_admin: bool) -> bool:
    """Admins see every chat; a client only sees their own order."""
    return is_admin or order.user_id == user_id


def unread_count(db: Session, *, order_id: int, is_admin: bool) -> int:
    order = db.get(Order, order_id)
    if order is None:
        return 0
    return order.unread_for(is_admin=is_admin)


# --- Live hub --------------------------------------------------------------


@dataclass(eq=False)
class Connection:
    """One open WebSocket bound to an order and an identity."""

    websocket: Any
    order_id: int
    user_id: int
    is_admin: bool
    # Serialises writes: two coroutines sending on one socket concurrently
    # would interleave frames.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, payload: dict[str, Any]) -> None:
        async with self.lock:
            await self.websocket.send_json(payload)


class ChatHub:
    """Fan-out of chat events to everyone watching an order."""

    def __init__(self) -> None:
        self._rooms: dict[int, set[Connection]] = {}

    def add(self, connection: Connection) -> None:
        self._rooms.setdefault(connection.order_id, set()).add(connection)
        presence.join(connection.order_id, connection.user_id, connection.is_admin)
        logger.info(
            "Chat connected: order_id=%s user_id=%s admin=%s watchers=%s",
            connection.order_id,
            connection.user_id,
            connection.is_admin,
            len(self._rooms[connection.order_id]),
        )

    def remove(self, connection: Connection) -> None:
        room = self._rooms.get(connection.order_id)
        if room:
            room.discard(connection)
            if not room:
                self._rooms.pop(connection.order_id, None)
        presence.leave(connection.order_id, connection.user_id, connection.is_admin)
        logger.info(
            "Chat disconnected: order_id=%s user_id=%s admin=%s",
            connection.order_id,
            connection.user_id,
            connection.is_admin,
        )

    def watchers(self, order_id: int) -> list[Connection]:
        return list(self._rooms.get(order_id, ()))

    async def broadcast_message(
        self, order_id: int, payload: dict[str, Any]
    ) -> None:
        """Send a message to the room, tailored per viewer.

        ``is_mine`` depends on who is looking, so the payload is copied and
        adjusted for each connection rather than shared.
        """
        for connection in self.watchers(order_id):
            tailored = dict(payload)
            tailored["is_mine"] = payload.get("sender_id") == connection.user_id
            await self._safe_send(
                connection, {"type": "message", "message": tailored}
            )

    async def broadcast_typing(
        self, order_id: int, *, sender: Connection, is_typing: bool, sender_name: str
    ) -> None:
        for connection in self.watchers(order_id):
            if connection is sender:
                continue
            await self._safe_send(
                connection,
                {
                    "type": "typing",
                    "is_typing": is_typing,
                    "sender_name": sender_name,
                },
            )

    async def _safe_send(
        self, connection: Connection, payload: dict[str, Any]
    ) -> None:
        """A dead socket must never break the broadcast for everyone else."""
        try:
            await connection.send(payload)
        except Exception:  # noqa: BLE001 - socket already gone
            logger.debug(
                "Dropping message to a closed socket: order_id=%s user_id=%s",
                connection.order_id,
                connection.user_id,
            )
            self.remove(connection)


hub = ChatHub()
