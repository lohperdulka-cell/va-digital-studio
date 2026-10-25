"""Outbound e-mail.

No SMTP transport is wired up yet, so every send is logged instead — that keeps
the support workflow testable end to end without an external dependency.  To go
live, set SMTP_* in the environment and replace ``_deliver`` with ``smtplib``.
"""

from __future__ import annotations

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def _deliver(*, to_email: str, subject: str, body: str) -> bool:
    """Placeholder transport. Logs the message and reports success."""
    logger.info(
        "EMAIL [stub] to=%s subject=%r length=%s from=%s",
        to_email,
        subject,
        len(body),
        settings.support_email,
    )
    return True


def send_support_reply(
    *, to_email: str, subject: str, body: str, ticket_id: int
) -> bool:
    """Notify a visitor that support answered their ticket."""
    return _deliver(
        to_email=to_email,
        subject=f"[Обращение #{ticket_id}] {subject}",
        body=body,
    )


def send_ticket_ack(*, to_email: str, subject: str, ticket_id: int) -> bool:
    """Acknowledge receipt of a new ticket."""
    return _deliver(
        to_email=to_email,
        subject=f"[Обращение #{ticket_id}] принято в работу",
        body=(
            "Спасибо за обращение! Мы получили ваш запрос и ответим "
            "в течение одного рабочего дня."
        ),
    )
