"""Shared Jinja2 environment and the ``render`` helper used by every router."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.errors import NotFoundError
from app.flash import get_flashed_messages
from app.formatting import format_money
from app.models.enums import OrderStatus, ServiceCategory, TicketStatus
from app.security.csrf import CSRF_FIELD_NAME, csrf_token_for

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# --- Filters ---------------------------------------------------------------


def money(value: Decimal | float | None) -> str:
    """Format a number as a rouble amount with thin-space thousands."""
    return format_money(value)


def plural(count: int, one: str, few: str, many: str) -> str:
    """Russian pluralisation: 1 заказ / 2 заказа / 5 заказов."""
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def date_ru(value: Any) -> str:
    """DD.MM.YYYY for datetimes and dates."""
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y")


def datetime_ru(value: Any) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M")


def time_short(value: Any) -> str:
    if value is None:
        return ""
    return value.strftime("%H:%M")


templates.env.filters["money"] = money
templates.env.filters["plural"] = plural
templates.env.filters["date_ru"] = date_ru
templates.env.filters["datetime_ru"] = datetime_ru
templates.env.filters["time_short"] = time_short

# --- Globals ---------------------------------------------------------------

templates.env.globals.update(
    settings=settings,
    app_name=settings.app_name,
    ServiceCategory=ServiceCategory,
    OrderStatus=OrderStatus,
    TicketStatus=TicketStatus,
    csrf_field_name=CSRF_FIELD_NAME,
)


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
):
    """Render ``template`` with the standard context every page needs."""
    payload: dict[str, Any] = {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "is_admin": getattr(request.state, "is_admin", False),
        "csrf_token": csrf_token_for(request),
        "flash_messages": get_flashed_messages(request),
        "path": request.url.path,
        "next_url": _safe_current_url(request),
        # Sidebar badges, set by the dashboard router's dependency.
        "nav_orders_unread": getattr(request.state, "nav_orders_unread", 0),
        "nav_chats_unread": getattr(request.state, "nav_chats_unread", 0),
        "nav_tickets_open": getattr(request.state, "nav_tickets_open", 0),
    }
    if context:
        payload.update(context)

    try:
        return templates.TemplateResponse(
            request, template, payload, status_code=status_code
        )
    except Exception as exc:  # TemplateNotFound and friends
        raise NotFoundError() from exc


def _safe_current_url(request: Request) -> str:
    """The current path+query, for ``?next=`` round-trips."""
    url = request.url.path
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url
