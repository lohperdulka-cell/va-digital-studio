"""Outbound e-mail over SMTP.

Configured from the environment; nothing is hard-coded.  When no host is set
the message is logged instead of sent, so development and the test suite work
without a mail server.  Delivery can run on a daemon thread: a slow SMTP server
must not hold a request open, and a failure must not turn a successful signup
into an error page.
"""

from __future__ import annotations

import smtplib
import ssl
import threading
from email.message import EmailMessage

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_SMTP_TIMEOUT_SECONDS = 15


def _build_message(*, to_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.resolved_email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    return message


def _deliver(*, to_email: str, subject: str, body: str) -> bool:
    """Send one message. Returns True on success, False on any failure."""
    if not settings.email_configured:
        # No SMTP configured: log the body so a developer can read the code.
        logger.info(
            "EMAIL [no SMTP configured] to=%s subject=%r\n%s", to_email, subject, body
        )
        return True

    message = _build_message(to_email=to_email, subject=subject, body=body)
    host = settings.resolved_email_host
    port = settings.resolved_email_port
    user = settings.resolved_email_user
    password = settings.resolved_email_password

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                host, port, timeout=_SMTP_TIMEOUT_SECONDS, context=context
            ) as server:
                if user:
                    server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                server.ehlo()
                if settings.email_use_tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if user:
                    server.login(user, password)
                server.send_message(message)
        logger.info("EMAIL sent to=%s subject=%r", to_email, subject)
        return True
    except Exception:
        # Never let a mail outage break the user's action.
        logger.exception("EMAIL delivery failed to=%s subject=%r", to_email, subject)
        return False


def send_async(*, to_email: str, subject: str, body: str) -> None:
    """Fire-and-forget delivery on a daemon thread."""
    threading.Thread(
        target=_deliver,
        kwargs={"to_email": to_email, "subject": subject, "body": body},
        daemon=True,
    ).start()


def _login_code_body(code: str) -> str:
    minutes = max(1, settings.login_code_ttl_seconds // 60)
    return (
        f"Ваш код для входа в {settings.app_name}: {code}\n\n"
        f"Код действует {minutes} мин. "
        "Если вы не запрашивали вход, просто проигнорируйте это письмо."
    )


def send_login_code(*, to_email: str, code: str) -> bool:
    """Send the six-digit sign-in code and wait for the result."""
    return _deliver(
        to_email=to_email,
        subject=f"Код для входа: {code}",
        body=_login_code_body(code),
    )


def send_login_code_async(*, to_email: str, code: str) -> None:
    """Non-blocking variant used by the request handler."""
    send_async(
        to_email=to_email,
        subject=f"Код для входа: {code}",
        body=_login_code_body(code),
    )


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
