"""Telegram login: a bot hands the user a code, the site redeems it.

Why a bot-delivered code rather than Telegram's Login Widget: the widget needs
a bot domain registered with BotFather and only works on HTTPS with a public
hostname, which a local or freshly-deployed instance does not have.  A code the
bot sends in the chat works everywhere the bot can reach Telegram's API.

The bot never sees a password and never touches the database directly — it
calls back into this service, which owns the code lifecycle.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.logging_config import get_logger
from app.security.tokens import create_telegram_start_token, decode_telegram_start_token
from app.services import login_codes

logger = get_logger(__name__)

_API_BASE = "https://api.telegram.org"
_TIMEOUT_SECONDS = 10


class TelegramError(Exception):
    """Raised when the Bot API call fails; the message is user-facing."""


def bot_username() -> str:
    """The @handle used to build the deep link, without the leading @."""
    configured = settings.telegram_bot_username.strip().lstrip("@")
    if configured:
        return configured
    return ""


def create_start_payload(email: str) -> str:
    """Signed ``/start`` payload that binds the chat to a known e-mail."""
    return create_telegram_start_token(normalize_email(email))


def read_start_payload(payload: str) -> str | None:
    """Return the e-mail inside a ``/start`` payload, or ``None`` if invalid."""
    claims = decode_telegram_start_token(payload)
    if claims is None:
        return None
    return claims.get("email") or None


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def deep_link(*, start_payload: str) -> str:
    """``https://t.me/<bot>?start=<payload>`` for the login button."""
    username = bot_username()
    if not username:
        return "https://t.me"
    return f"https://t.me/{username}?start={start_payload}"


def send_message(*, chat_id: str, text: str) -> bool:
    """Send a plain message through the Bot API.

    Returns False instead of raising when the bot is unconfigured or the call
    fails, so a Telegram outage cannot break a page that merely tries to notify.
    """
    token = settings.telegram_bot_token.strip()
    if not token:
        logger.warning("Telegram send skipped: TELEGRAM_BOT_TOKEN is unset")
        return False

    try:
        response = httpx.post(
            f"{_API_BASE}/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            logger.warning("Telegram API refused the message: %s", payload.get("description"))
            return False
        return True
    except Exception:
        logger.exception("Telegram send failed for chat_id=%s", chat_id)
        return False


def send_login_code(*, chat_id: str, code: str) -> bool:
    """Deliver the sign-in code into the Telegram chat."""
    minutes = max(1, settings.login_code_ttl_seconds // 60)
    return send_message(
        chat_id=chat_id,
        text=(
            f"Код для входа в {settings.app_name}: {code}\n"
            f"Код действует {minutes} мин.\n\n"
            "Если вы не запрашивали вход, просто проигнорируйте это сообщение."
        ),
    )


def issue_code_for_chat(
    db, *, email: str, chat_id: str, username: str = ""
) -> str:
    """Create a Telegram-channel code and try to deliver it."""
    code = login_codes.issue_code(
        db,
        email=email,
        channel=login_codes.CHANNEL_TELEGRAM,
        telegram_id=chat_id,
        telegram_username=username,
    )
    send_login_code(chat_id=chat_id, code=code)
    return code
