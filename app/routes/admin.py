"""Administrator dashboard: orders, chats, support tickets, services, news.

Every route here is gated by ``CurrentAdmin`` at router level, so a signed-in
non-admin receives 403 before any handler runs.  Mutations are POST-only and
pass through the shared CSRF dependency.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.flash import flash
from app.logging_config import get_logger
from app.models import Order
from app.models.enums import OrderStatus, ServiceCategory, TicketStatus
from app.schemas.forms import NewsForm, ServiceForm, TicketReplyForm
from app.security.csrf import require_csrf
from app.security.deps import CurrentAdmin, DbSession
from app.security.sanitize import clean_slug
from app.security.sessions import get_current_admin
from app.services import catalog as catalog_service
from app.services import chat as chat_service
from app.services import dashboard as dashboard_service
from app.services import newsfeed as news_service
from app.services import orders as order_service
from app.services import support as support_service
from app.templating import render

logger = get_logger(__name__)

# get_current_admin runs first so an anonymous request is redirected to sign-in
# rather than tripping the CSRF check and getting an opaque 403.
async def attach_nav_counts(
    request: Request, admin: CurrentAdmin, db: DbSession
) -> None:
    """Publish the sidebar badges on ``request.state``.

    Every dashboard page shows the same unread/open counters, so they are
    computed once here instead of being passed by each route.
    """
    stats = dashboard_service.stats(db)
    request.state.nav_orders_unread = stats.chats_unread
    request.state.nav_chats_unread = stats.chats_unread
    request.state.nav_tickets_open = stats.tickets_open


router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[
        Depends(get_current_admin),
        Depends(require_csrf),
        Depends(attach_nav_counts),
    ],
)


def _redirect(path: str) -> RedirectResponse:
    """POST/Redirect/GET after a successful mutation."""
    return RedirectResponse(path, status_code=303)


# --- Overview --------------------------------------------------------------


@router.get("")
def overview(request: Request, admin: CurrentAdmin, db: DbSession):
    stats = dashboard_service.stats(db)
    recent_orders = order_service.list_all(db, limit=8)
    unread = dashboard_service.unread_counts(db, is_admin=True)
    return render(
        request,
        "dashboard/overview.html",
        {
            "stats": stats,
            "recent_orders": recent_orders,
            "unread": unread,
            "open_tickets": support_service.list_tickets(
                db, status=TicketStatus.OPEN, limit=5
            ),
        },
    )


# --- Orders ----------------------------------------------------------------


@router.get("/orders")
def orders(
    request: Request,
    admin: CurrentAdmin,
    db: DbSession,
    status: str = Query(default=""),
    q: str = Query(default="", max_length=120),
):
    selected = _parse_status(status)
    items = order_service.list_all(db, status=selected, query=q)
    return render(
        request,
        "dashboard/orders.html",
        {
            "orders": items,
            "status": selected,
            "query": q,
            "statuses": list(OrderStatus),
            "unread": dashboard_service.unread_counts(db, is_admin=True),
        },
    )


@router.get("/orders/{order_id}")
def order_detail(
    request: Request,
    order_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    order = order_service.get_order_with_messages(db, order_id)
    if order is None:
        raise NotFoundError(detail="Заказ не найден")
    return render(
        request,
        "dashboard/order_detail.html",
        {
            "order": order,
            "statuses": list(OrderStatus),
            "messages": chat_service.load_history(db, order_id),
            "ws_path": f"/ws/chat/{order_id}",
        },
    )


@router.post("/orders/{order_id}/status")
def change_status(
    request: Request,
    order_id: int,
    admin: CurrentAdmin,
    db: DbSession,
    status: str = Form(...),
):
    order = _require_order(db, order_id)
    new_status = _parse_status(status)
    if new_status is None:
        flash(request, "Неизвестный статус", "error")
        return _redirect(f"/dashboard/orders/{order_id}")

    order_service.update_status(db, order, new_status)
    flash(request, f"Статус заказа №{order_id}: {new_status.label}", "success")
    return _redirect(f"/dashboard/orders/{order_id}")


@router.post("/orders/{order_id}/price")
def change_price(
    request: Request,
    order_id: int,
    admin: CurrentAdmin,
    db: DbSession,
    price: str = Form(default=""),
):
    order = _require_order(db, order_id)
    try:
        order_service.set_price(db, order, price)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _redirect(f"/dashboard/orders/{order_id}")

    flash(request, f"Стоимость заказа №{order_id} обновлена", "success")
    return _redirect(f"/dashboard/orders/{order_id}")


# --- Chats -----------------------------------------------------------------


@router.get("/chats")
def chats(request: Request, admin: CurrentAdmin, db: DbSession):
    conversations = dashboard_service.conversations(db)
    order_ids = [order.id for order in conversations]
    return render(
        request,
        "dashboard/chats.html",
        {
            "conversations": conversations,
            "unread": dashboard_service.unread_counts(db, is_admin=True),
            "previews": dashboard_service.last_messages(db, order_ids),
        },
    )


# --- Support ---------------------------------------------------------------


@router.get("/support")
def support(
    request: Request,
    admin: CurrentAdmin,
    db: DbSession,
    status: str = Query(default=""),
):
    selected = _parse_ticket_status(status)
    return render(
        request,
        "dashboard/support.html",
        {
            "tickets": support_service.list_tickets(db, status=selected),
            "status": selected,
        },
    )


@router.get("/support/{ticket_id}")
def support_detail(
    request: Request,
    ticket_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    ticket = support_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise NotFoundError(detail="Обращение не найдено")
    return render(request, "dashboard/support_detail.html", {"ticket": ticket})


@router.post("/support/{ticket_id}/reply")
def support_reply(
    request: Request,
    ticket_id: int,
    admin: CurrentAdmin,
    db: DbSession,
    body: str = Form(default=""),
):
    ticket = support_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise NotFoundError(detail="Обращение не найдено")

    try:
        payload = TicketReplyForm(body=body)
    except ValidationError as exc:
        flash(request, _first_error(exc), "error")
        return _redirect(f"/dashboard/support/{ticket_id}")

    support_service.add_staff_reply(db, ticket=ticket, body=payload.body, staff=admin)
    flash(request, f"Ответ по обращению №{ticket_id} отправлен", "success")
    return _redirect(f"/dashboard/support/{ticket_id}")


@router.post("/support/{ticket_id}/reopen")
def support_reopen(
    request: Request,
    ticket_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    ticket = support_service.get_ticket(db, ticket_id)
    if ticket is None:
        raise NotFoundError(detail="Обращение не найдено")
    support_service.reopen(db, ticket)
    flash(request, f"Обращение №{ticket_id} открыто заново", "info")
    return _redirect(f"/dashboard/support/{ticket_id}")


# --- Services --------------------------------------------------------------


@router.get("/services")
def services(request: Request, admin: CurrentAdmin, db: DbSession):
    return render(
        request,
        "dashboard/services.html",
        {
            "services": catalog_service.list_all_services(db),
            "categories": list(ServiceCategory),
        },
    )


@router.get("/services/new")
def service_new(request: Request, admin: CurrentAdmin):
    return render(
        request,
        "dashboard/service_form.html",
        {
            "service": None,
            "categories": list(ServiceCategory),
            "form": {},
        },
    )


@router.get("/services/{service_id}")
def service_edit(
    request: Request,
    service_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    service = catalog_service.get_service(db, service_id)
    if service is None:
        raise NotFoundError(detail="Услуга не найдена")
    return render(
        request,
        "dashboard/service_form.html",
        {
            "service": service,
            "categories": list(ServiceCategory),
            "form": {
                "slug": service.slug,
                "title": service.title,
                "short_description": service.short_description,
                "description": service.description,
                "category": service.category,
                "tags": ", ".join(service.tags or []),
                "price_from": service.price_from,
                "duration_days": service.duration_days,
                "icon": service.icon,
                "is_active": service.is_active,
                "is_featured": service.is_featured,
                "sort_order": service.sort_order,
            },
        },
    )


@router.post("/services/save")
async def service_save(
    request: Request,
    admin: CurrentAdmin,
    db: DbSession,
):
    """Create or update a service from the shared form.

    The form posts ``service_id`` to distinguish the two cases; one endpoint
    keeps the create and edit templates identical.
    """
    raw = await request.form()
    service_id = str(raw.get("service_id") or "").strip()

    try:
        payload = ServiceForm(
            slug=str(raw.get("slug") or ""),
            title=str(raw.get("title") or ""),
            short_description=str(raw.get("short_description") or ""),
            description=str(raw.get("description") or ""),
            category=str(raw.get("category") or ServiceCategory.SITES.value),
            tags=str(raw.get("tags") or ""),
            price_from=str(raw.get("price_from") or "0"),
            duration_days=str(raw.get("duration_days") or "14"),
            icon=str(raw.get("icon") or "🚀"),
            is_active=_checkbox(raw, "is_active"),
            is_featured=_checkbox(raw, "is_featured"),
            sort_order=str(raw.get("sort_order") or "0"),
        )
    except ValidationError as exc:
        flash(request, _first_error(exc), "error")
        target = (
            f"/dashboard/services/{service_id}"
            if service_id
            else "/dashboard/services/new"
        )
        return _redirect(target)

    data = {
        "slug": payload.slug or clean_slug(payload.title),
        "title": payload.title,
        "short_description": payload.short_description,
        "description": payload.description,
        "category": payload.category,
        "tags": payload.tags,
        "price_from": payload.price_from,
        "duration_days": payload.duration_days,
        "icon": payload.icon,
        "is_active": payload.is_active,
        "is_featured": payload.is_featured,
        "sort_order": payload.sort_order,
    }

    if service_id:
        service = catalog_service.get_service(db, int(service_id))
        if service is None:
            raise NotFoundError(detail="Услуга не найдена")
        catalog_service.update_service(db, service, data)
        flash(request, f"Услуга «{service.title}» обновлена", "success")
    else:
        service = catalog_service.create_service(db, data)
        flash(request, f"Услуга «{service.title}» создана", "success")

    return _redirect("/dashboard/services")


@router.post("/services/{service_id}/delete")
def service_delete(
    request: Request,
    service_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    service = catalog_service.get_service(db, service_id)
    if service is None:
        raise NotFoundError(detail="Услуга не найдена")
    title = service.title
    catalog_service.delete_service(db, service)
    flash(request, f"Услуга «{title}» удалена", "info")
    return _redirect("/dashboard/services")


# --- News ------------------------------------------------------------------


@router.get("/news")
def news(request: Request, admin: CurrentAdmin, db: DbSession):
    return render(
        request, "dashboard/news.html", {"news": news_service.list_all_news(db)}
    )


@router.get("/news/new")
def news_new(request: Request, admin: CurrentAdmin):
    return render(
        request, "dashboard/news_form.html", {"item": None, "form": {}}
    )


@router.get("/news/{news_id}")
def news_edit(
    request: Request,
    news_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    item = news_service.get_news(db, news_id)
    if item is None:
        raise NotFoundError(detail="Новость не найдена")
    return render(
        request,
        "dashboard/news_form.html",
        {
            "item": item,
            "form": {
                "slug": item.slug,
                "title": item.title,
                "preview": item.preview,
                "body": item.body,
                "cover_emoji": item.cover_emoji,
                "is_published": item.is_published,
            },
        },
    )


@router.post("/news/save")
async def news_save(
    request: Request,
    admin: CurrentAdmin,
    db: DbSession,
):
    raw = await request.form()
    news_id = str(raw.get("news_id") or "").strip()

    try:
        payload = NewsForm(
            slug=str(raw.get("slug") or ""),
            title=str(raw.get("title") or ""),
            preview=str(raw.get("preview") or ""),
            body=str(raw.get("body") or ""),
            cover_emoji=str(raw.get("cover_emoji") or "📰"),
            is_published=_checkbox(raw, "is_published"),
        )
    except ValidationError as exc:
        flash(request, _first_error(exc), "error")
        target = f"/dashboard/news/{news_id}" if news_id else "/dashboard/news/new"
        return _redirect(target)

    data = {
        "slug": payload.slug or clean_slug(payload.title),
        "title": payload.title,
        "preview": payload.preview,
        "body": payload.body,
        "cover_emoji": payload.cover_emoji,
        "is_published": payload.is_published,
    }

    if news_id:
        item = news_service.get_news(db, int(news_id))
        if item is None:
            raise NotFoundError(detail="Новость не найдена")
        news_service.update_news(db, item, data)
        flash(request, f"Новость «{item.title}» обновлена", "success")
    else:
        item = news_service.create_news(db, data)
        flash(request, f"Новость «{item.title}» создана", "success")

    return _redirect("/dashboard/news")


@router.post("/news/{news_id}/delete")
def news_delete(
    request: Request,
    news_id: int,
    admin: CurrentAdmin,
    db: DbSession,
):
    item = news_service.get_news(db, news_id)
    if item is None:
        raise NotFoundError(detail="Новость не найдена")
    title = item.title
    news_service.delete_news(db, item)
    flash(request, f"Новость «{title}» удалена", "info")
    return _redirect("/dashboard/news")


# --- Helpers ---------------------------------------------------------------


def _parse_status(value: str) -> OrderStatus | None:
    """Tolerant status parsing: an unknown filter shows everything."""
    if not value:
        return None
    try:
        return OrderStatus(value)
    except ValueError:
        return None


def _parse_ticket_status(value: str) -> TicketStatus | None:
    if not value:
        return None
    try:
        return TicketStatus(value)
    except ValueError:
        return None


def _checkbox(raw: Any, name: str) -> bool:
    """Read an HTML checkbox.

    An unchecked box is simply absent from the payload, so anything other than
    an explicit affirmative value means False.
    """
    value = raw.get(name)
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _require_order(db: Session, order_id: int) -> Order:
    order = order_service.get_order(db, order_id)
    if order is None:
        raise NotFoundError(detail="Заказ не найден")
    return order


def _first_error(exc: ValidationError) -> str:
    """Turn a Pydantic ValidationError into one readable line."""
    first = exc.errors()[0]
    message = str(first.get("msg", "Некорректное значение"))
    return message.removeprefix("Value error, ")
