"""Aggregate queries backing the administrator dashboard.

Kept separate from the per-entity services so the dashboard can fetch its
overview numbers and unread counters in a handful of grouped queries instead
of walking every row in Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import ChatMessage, Order, SupportTicket, User
from app.models.enums import MessageKind, OrderStatus, TicketStatus
from app.services.orders import ACTIVE_STATUSES


@dataclass(frozen=True)
class DashboardStats:
    orders_total: int
    orders_active: int
    orders_done: int
    tickets_open: int
    chats_unread: int
    revenue: float
    clients: int


def _unread_condition(is_admin: bool):
    """SQL predicate matching messages the viewing side has not read yet.

    A client's unread messages are the staff/system ones, an administrator's
    are the client ones — mirroring ``Order.unread_for`` but expressed as SQL
    so the whole dashboard costs one grouped query rather than N.
    """
    opposite = (
        ChatMessage.kind.in_([MessageKind.STAFF, MessageKind.SYSTEM])
        if not is_admin
        else ChatMessage.kind == MessageKind.CLIENT
    )
    return ChatMessage.is_read.is_(False) & opposite


def unread_counts(db: Session, *, is_admin: bool) -> dict[int, int]:
    """``{order_id: unread_count}`` for one side, in a single query."""
    rows = db.execute(
        select(ChatMessage.order_id, func.count(ChatMessage.id))
        .where(_unread_condition(is_admin))
        .group_by(ChatMessage.order_id)
    )
    return {order_id: int(count) for order_id, count in rows}


def stats(db: Session) -> DashboardStats:
    """Headline counters for the dashboard overview page."""
    orders_total = int(db.scalar(select(func.count(Order.id))) or 0)
    orders_active = int(
        db.scalar(
            select(func.count(Order.id)).where(Order.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )
    tickets_open = int(
        db.scalar(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status == TicketStatus.OPEN
            )
        )
        or 0
    )
    condition = _unread_condition(is_admin=True)
    chats_unread = int(
        db.scalar(select(func.count(ChatMessage.id)).where(condition)) or 0
    )
    # Only completed orders count towards revenue — drafts and cancellations
    # would overstate it.
    revenue = db.scalar(
        select(func.coalesce(func.sum(Order.price_final), 0)).where(
            Order.status == OrderStatus.DONE
        )
    )
    clients = int(db.scalar(select(func.count(User.id))) or 0)

    return DashboardStats(
        orders_total=orders_total,
        orders_active=orders_active,
        orders_done=orders_total - orders_active,
        tickets_open=tickets_open,
        chats_unread=chats_unread,
        revenue=float(revenue or 0),
        clients=clients,
    )


def conversations(db: Session, *, limit: int = 100) -> list[Order]:
    """Orders that have at least one message, busiest first.

    Orders with no messages are excluded: an empty room is not a conversation.
    """
    latest = func.max(ChatMessage.created_at).label("last_at")
    statement = (
        select(Order)
        .join(ChatMessage, ChatMessage.order_id == Order.id)
        .options(selectinload(Order.user), selectinload(Order.service))
        .group_by(Order.id)
        .order_by(latest.desc(), Order.id.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


@dataclass(frozen=True)
class MessagePreview:
    text: str
    created_at: datetime


def last_messages(db: Session, order_ids: list[int]) -> dict[int, MessagePreview]:
    """``{order_id: newest message}`` so the chat list can show a preview.

    One query for the whole page: the newest ``created_at`` per order, then the
    row that carries it.  ``id`` breaks ties between same-second messages.
    """
    if not order_ids:
        return {}

    newest = (
        select(
            ChatMessage.order_id.label("order_id"),
            func.max(ChatMessage.created_at).label("created_at"),
        )
        .where(ChatMessage.order_id.in_(order_ids))
        .group_by(ChatMessage.order_id)
        .subquery()
    )
    rows = db.scalars(
        select(ChatMessage)
        .join(
            newest,
            (ChatMessage.order_id == newest.c.order_id)
            & (ChatMessage.created_at == newest.c.created_at),
        )
        .order_by(ChatMessage.id.desc())
    )
    previews: dict[int, MessagePreview] = {}
    for message in rows:
        previews.setdefault(
            message.order_id,
            MessagePreview(text=message.text, created_at=message.created_at),
        )
    return previews
