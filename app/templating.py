"""Shared Jinja2 environment and the ``render`` helper used by every router."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.errors import NotFoundError
from app.flash import get_flashed_messages
from app.formatting import format_money
from app.i18n import (
    LOCALE_QUERY_PARAM,
    count_label,
    get_locale,
    other_locale,
    t,
)
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
    """Noun form for ``count``: Russian rules, or the English two-form rule.

    Templates pass the three Russian forms.  For English the singular and the
    plural are looked up in the catalogue, so "1 услуга" becomes "1 service"
    instead of leaking the Russian noun into an English page.
    """
    return count_label(count, one, few, many, t(one), t(many))


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
    # Interface translation; Russian is the default and returns the source.
    t=t,
    get_locale=get_locale,
    other_locale=other_locale,
    LOCALE_QUERY_PARAM=LOCALE_QUERY_PARAM,
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
        "flash_messages": _translate_flashes(get_flashed_messages(request)),
        "path": request.url.path,
        "next_url": _safe_current_url(request),
        "locale": get_locale(),
        "locale_switch_url": _locale_switch_url(request),
        # Sidebar badges, set by the dashboard router's dependency.
        "nav_orders_unread": getattr(request.state, "nav_orders_unread", 0),
        "nav_chats_unread": getattr(request.state, "nav_chats_unread", 0),
        "nav_tickets_open": getattr(request.state, "nav_tickets_open", 0),
        "nav_reviews_pending": getattr(request.state, "nav_reviews_pending", 0),
    }
    if context:
        payload.update(context)

    try:
        return templates.TemplateResponse(
            request, template, payload, status_code=status_code
        )
    except Exception as exc:  # TemplateNotFound and friends
        raise NotFoundError() from exc


def _translate_flashes(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate queued messages at render time.

    A message is created by the route that handled the POST and shown after the
    redirect, so translating here — not when the message is queued — makes it
    follow the language of the page the visitor actually lands on.  Messages
    built with f-strings simply fall back to Russian.
    """
    return [{**item, "message": t(item["message"])} for item in messages]


def _safe_current_url(request: Request) -> str:
    """The current path+query, for ``?next=`` round-trips."""
    url = request.url.path
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _locale_switch_url(request: Request) -> str:
    """Link to the same page in the other language.

    Keeps every existing query parameter — a catalog filter or a page number
    must survive a language switch — and only replaces ``lang``.
    """
    params = dict(request.query_params)
    params[LOCALE_QUERY_PARAM] = other_locale()
    query = urlencode(params)
    return f"{request.url.path}?{query}" if query else request.url.path
