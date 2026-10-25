"""Support tickets raised from the public site."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.logging_config import get_logger
from app.models import SupportMessage, SupportTicket, User
from app.models.enums import TicketStatus
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
) -> SupportTicket:
    """Create a ticket plus its first message."""
    ticket = SupportTicket(
        user_id=user.id if user else None,
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
        "Support ticket created: id=%s email=%s user_id=%s",
        ticket.id,
        ticket.email,
        user.id if user else None,
    )
    return ticket


def get_ticket(db: Session, ticket_id: int) -> SupportTicket | None:
    return db.scalar(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.thread), selectinload(SupportTicket.user))
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
