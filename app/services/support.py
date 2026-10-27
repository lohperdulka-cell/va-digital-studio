"""Support tickets raised from the public site."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.logging_config import get_logger
from app.models import Order, SupportMessage, SupportTicket, User
from app.models.enums import OrderStatus, TicketStatus
from app.security.sanitize import clean_email, clean_plain_text

logger = get_logger(__name__)


def create_ticket(
    db: Session,
    *,
    subject: str,
    message: str,
    email: str,
    name: str = "",
    user: User | None = None,
    order_id: int | None = None,
) -> SupportTicket:
    """Create a ticket plus its first message.

    ``order_id`` links the enquiry to an order when the visitor supplied one.
    Only an order the visitor actually owns is accepted, so a guessed number
    cannot attach a ticket to somebody else's order.
    """
    if order_id is not None and user is not None:
        owned = db.scalar(
            select(Order.id).where(Order.id == order_id, Order.user_id == user.id)
        )
        if owned is None:
            order_id = None

    ticket = SupportTicket(
        user_id=user.id if user else None,
        order_id=order_id,
        email=clean_email(user.email if user and not email else email),
        name=clean_plain_text(name, max_length=200)
        or (user.display_name if user else ""),
        subject=clean_plain_text(subject, max_length=200),
        message=clean_plain_text(message, max_length=5000),
        status=TicketStatus.OPEN,
    )
    db.add(ticket)
    db.flush()

    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_id=user.id if user else None,
            body=ticket.message,
            is_staff=False,
        )
    )
    db.commit()
    db.refresh(ticket)
    logger.info(
        "Support ticket created: id=%s email=%s user_id=%s order_id=%s",
        ticket.id,
        ticket.email,
        user.id if user else None,
        order_id,
    )
    return ticket


def get_ticket(db: Session, ticket_id: int) -> SupportTicket | None:
    return db.scalar(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(
            selectinload(SupportTicket.thread),
            selectinload(SupportTicket.user),
            selectinload(SupportTicket.order),
        )
    )


def list_tickets(
    db: Session, *, status: TicketStatus | None = None, limit: int = 200
) -> list[SupportTicket]:
    statement = (
        select(SupportTicket)
        .options(selectinload(SupportTicket.thread))
        .order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
    )
    if status is not None:
        statement = statement.where(SupportTicket.status == status)
    return list(db.scalars(statement.limit(limit)))


def list_for_user(db: Session, user_id: int, *, limit: int = 20) -> list[SupportTicket]:
    statement = (
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def count_open(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.status == TicketStatus.OPEN
            )
        )
        or 0
    )


def add_staff_reply(
    db: Session, *, ticket: SupportTicket, body: str, staff: User
) -> SupportMessage:
    """Record an answer and hand it to the mailer."""
    from app.services import mailer

    reply = SupportMessage(
        ticket_id=ticket.id,
        sender_id=staff.id,
        body=clean_plain_text(body, max_length=5000),
        is_staff=True,
    )
    db.add(reply)

    ticket.admin_reply = reply.body
    ticket.replied_at = func.now()
    ticket.status = TicketStatus.CLOSED
    db.commit()
    db.refresh(reply)

    logger.info(
        "Support reply sent: ticket_id=%s staff_id=%s", ticket.id, staff.id
    )
    mailer.send_support_reply(
        to_email=ticket.email,
        subject=ticket.subject,
        body=reply.body,
        ticket_id=ticket.id,
    )
    return reply


def reopen(db: Session, ticket: SupportTicket) -> SupportTicket:
    ticket.status = TicketStatus.OPEN
    db.commit()
    db.refresh(ticket)
    logger.info("Support ticket reopened: id=%s", ticket.id)
    return ticket


def reopen_order_for_support(
    db: Session, *, ticket: SupportTicket, price: str | None = None
) -> Order | None:
    """Move a linked, finished order back to "Поддержка" and reopen its chat.

    Support work is quoted separately from the original job, so the price is
    set to 0 by default — the order stays billable, just at no extra charge —
    and staff may override it when the follow-up is substantial.
    """
    from app.services import orders as order_service

    if ticket.order_id is None:
        return None

    order = db.get(Order, ticket.order_id)
    if order is None:
        return None

    raw = (price or "").strip() or "0"
    try:
        order_service.set_price(db, order, raw)
    except ValueError:
        logger.warning("Support price rejected: order_id=%s value=%r", order.id, price)
        raise

    order_service.update_status(db, order, OrderStatus.SUPPORT)
    db.refresh(order)
    logger.info("Order reopened for support: order_id=%s ticket_id=%s", order.id, ticket.id)
    return order
