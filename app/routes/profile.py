"""Profile pages and order creation for the signed-in user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.errors import ForbiddenError, NotFoundError
from app.flash import flash
from app.logging_config import get_logger
from app.security.csrf import require_csrf
from app.security.deps import CurrentUser, DbSession
from app.security.sessions import get_current_user
from app.security.tokens import safe_next_path
from app.services import catalog as catalog_service
from app.services import orders as order_service
from app.templating import render

logger = get_logger(__name__)

# Authentication runs before CSRF so an anonymous POST is answered with a login
# redirect rather than a confusing 403; require_csrf is a no-op on GET.
router = APIRouter(
    tags=["profile"],
    dependencies=[Depends(get_current_user), Depends(require_csrf)],
)


@router.get("/profile")
def profile(
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    orders = order_service.list_for_user(db, user.id, limit=10)
    return render(
        request,
        "profile.html",
        {
            "orders": orders,
            "order_stats": order_service.stats_for_user(db, user.id),
        },
    )


@router.get("/profile/orders")
def my_orders(
    request: Request,
    user: CurrentUser,
    db: DbSession,
):
    return render(
        request,
        "orders_list.html",
        {"orders": order_service.list_for_user(db, user.id)},
    )


@router.get("/profile/orders/{order_id}")
def order_detail(
    request: Request,
    order_id: int,
    user: CurrentUser,
    db: DbSession,
):
    order = order_service.get_order_with_messages(db, order_id)
    if order is None:
        raise NotFoundError(detail="Заказ не найден")
    # Ownership check: an administrator sees it in the dashboard instead.
    if order.user_id != user.id and not user.is_admin:
        logger.warning(
            "Order access denied: order_id=%s owner=%s requester=%s",
            order_id,
            order.user_id,
            user.id,
        )
        raise ForbiddenError(detail="Этот заказ принадлежит другому пользователю")

    return render(request, "order_detail.html", {"order": order})


@router.post("/orders")
def create_order(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    service_id: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    next: str = Form(""),
):
    """Create a draft order from a «Заказать» button and open its chat."""
    service = None
    if service_id.strip():
        try:
            service = catalog_service.get_service(db, int(service_id))
        except ValueError:
            service = None

    order = order_service.create_draft(
        db,
        user=user,
        service=service,
        title=title or (service.title if service else ""),
        description=description,
    )

    flash(
        request,
        f"Заказ №{order.id} создан. Опишите задачу в чате — менеджер ответит там же.",
        "success",
    )

    target = safe_next_path(next, default=f"/chat/{order.id}")
    # Only bounce back to a catalogue page; anything else goes to the chat.
    if target.startswith("/catalog"):
        return RedirectResponse(target, status_code=303)
    return RedirectResponse(f"/chat/{order.id}", status_code=303)
