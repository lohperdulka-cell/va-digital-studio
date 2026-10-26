"""Outbound e-mail.

Two transports, chosen by configuration:

* **HTTP API** (Resend or Brevo) — the only option on Render's free plan, which
  blocks outbound SMTP ports 25/465/587 outright.
* **SMTP** — for paid plans, self-hosting and local work.

When neither is configured the message is logged instead of sent, so
development and the test suite work without a mail server.  That fallback is
disabled in production: writing a sign-in code to the deploy log is a
misconfiguration, not a convenience, so delivery reports failure instead and
the caller tells the user.

Delivery is synchronous and bounded by a timeout: a failure is never allowed to
turn a successful signup into an error page, but the caller does learn whether
the message went out.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_SMTP_TIMEOUT_SECONDS = 15
_API_TIMEOUT_SECONDS = 15


def _build_message(*, to_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.resolved_email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    return message


def _deliver_api(*, to_email: str, subject: str, body: str) -> bool:
    """Send over an HTTPS mail API. Returns True on success."""
    provider = settings.email_api_provider.strip().lower()
    sender = settings.resolved_email_from
    if provider == "resend":
        url = "https://api.resend.com/emails"
        headers = {"Authorization": f"Bearer {settings.email_api_key}"}
        payload = {
            "from": sender,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
    elif provider == "brevo":
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {"api-key": settings.email_api_key}
        payload = {
            "sender": {"email": sender},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        }
    else:
        logger.error("EMAIL not sent: unknown EMAIL_API_PROVIDER=%r", provider)
        return False

    with httpx.Client(timeout=_API_TIMEOUT_SECONDS) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    logger.info("EMAIL sent to=%s via %s", to_email, provider)
    return True


def _deliver_smtp(*, to_email: str, subject: str, body: str) -> bool:
    """Send over SMTP. Returns True on success."""
    message = _build_message(to_email=to_email, subject=subject, body=body)
    host = settings.resolved_email_host
    port = settings.resolved_email_port
    user = settings.resolved_email_user
    password = settings.resolved_email_password

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
    logger.info("EMAIL sent to=%s via smtp", to_email)
    return True


def _deliver(*, to_email: str, subject: str, body: str) -> bool:
    """Send one message. Returns True on success, False on any failure."""
    if not settings.email_configured:
        if settings.is_production:
            # In production an unconfigured mailer is a misconfiguration, not a
            # convenience: logging the body would write sign-in codes to the
            # deploy log.  Report the failure so the caller can tell the user.
            # The subject can carry the sign-in code, so log the recipient only.
            logger.error(
                "EMAIL not sent: no mail transport configured (set EMAIL_API_"
                "PROVIDER/EMAIL_API_KEY, or SMTP_HOST/SMTP_USER/SMTP_PASSWORD). "
                "to=%s",
                to_email,
            )
            return False
        # Development and tests: no mail server, so log the body instead of
        # sending it and let the developer read the code from the console.
        logger.info(
            "EMAIL [no transport configured] to=%s subject=%r\n%s",
            to_email,
            subject,
            body,
        )
        return True

    try:
        if settings.email_api_configured:
            return _deliver_api(to_email=to_email, subject=subject, body=body)
        return _deliver_smtp(to_email=to_email, subject=subject, body=body)
    except Exception:
        # Never let a mail outage break the user's action.  Log the recipient
        # only: the subject and body can carry a sign-in code.
        logger.exception("EMAIL delivery failed to=%s", to_email)
        return False


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
