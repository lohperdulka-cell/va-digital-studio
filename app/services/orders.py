"""Order lifecycle: creation, listing, status and price updates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.formatting import format_money
from app.logging_config import get_logger
from app.models import Order, Service, User
from app.models.enums import MessageKind, OrderStatus
from app.security.sanitize import clean_plain_text

logger = get_logger(__name__)

TITLE_MAX = 200
DESCRIPTION_MAX = 4000


@dataclass(frozen=True)
class OrderStats:
    total: int
    active: int
    done: int


ACTIVE_STATUSES = (
    OrderStatus.DRAFT,
    OrderStatus.DISCUSSING,
    OrderStatus.IN_PROGRESS,
    OrderStatus.REVIEW,
)


def create_draft(
    db: Session,
    *,
    user: User,
    service: Service | None = None,
    title: str = "",
    description: str = "",
) -> Order:
    """Create a draft order and its opening system message."""
    from app.models import ChatMessage

    clean_title = clean_plain_text(title, max_length=TITLE_MAX)
    if not clean_title:
        clean_title = service.title if service else "Индивидуальный проект"

    order = Order(
        user_id=user.id,
        service_id=service.id if service else None,
        title=clean_title,
        description=clean_plain_text(description, max_length=DESCRIPTION_MAX),
        status=OrderStatus.DRAFT,
    )
    db.add(order)
    db.flush()

    db.add(
        ChatMessage(
            order_id=order.id,
            sender_id=None,
            kind=MessageKind.SYSTEM,
            text=(
                f"Заказ #{order.id} создан. Опишите задачу — менеджер ответит "
                "в этом чате и согласует стоимость."
            ),
        )
    )
    db.commit()
    db.refresh(order)
    logger.info(
        "Order created: id=%s user_id=%s service_id=%s",
        order.id,
        user.id,
        service.id if service else None,
    )
    return order


def get_order(db: Session, order_id: int) -> Order | None:
    return db.get(Order, order_id)


def get_order_with_messages(db: Session, order_id: int) -> Order | None:
    return db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.messages), selectinload(Order.service))
    )


def list_for_user(db: Session, user_id: int, *, limit: int | None = None) -> list[Order]:
    statement = (
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.service), selectinload(Order.messages))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement))


def stats_for_user(db: Session, user_id: int) -> OrderStats:
    total = int(
        db.scalar(select(func.count(Order.id)).where(Order.user_id == user_id)) or 0
    )
    active = int(
        db.scalar(
            select(func.count(Order.id)).where(
                Order.user_id == user_id, Order.status.in_(ACTIVE_STATUSES)
            )
        )
        or 0
    )
    return OrderStats(total=total, active=active, done=total - active)


def list_all(
    db: Session,
    *,
    status: OrderStatus | None = None,
    query: str = "",
    limit: int = 200,
) -> list[Order]:
    """Dashboard listing with optional status filter and free-text search."""
    statement = (
        select(Order)
        .options(selectinload(Order.service), selectinload(Order.user))
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if status is not None:
        statement = statement.where(Order.status == status)

    needle = clean_plain_text(query, max_length=120)
    if needle:
        pattern = f"%{needle}%"
        statement = statement.join(User, Order.user_id == User.id).where(
            or_(
                Order.title.ilike(pattern),
                Order.description.ilike(pattern),
                User.email.ilike(pattern),
                User.name.ilike(pattern),
            )
        )

    return list(db.scalars(statement.limit(limit)))


def update_status(db: Session, order: Order, status: OrderStatus) -> Order:
    """Change status and leave an audit trail in the chat."""
    from app.models import ChatMessage

    if order.status == status:
        return order

    previous = order.status
    order.status = status
    db.add(
        ChatMessage(
            order_id=order.id,
            sender_id=None,
            kind=MessageKind.SYSTEM,
            text=f"Статус изменён: {previous.label} → {status.label}",
        )
    )
    db.commit()
    db.refresh(order)
    logger.info(
        "Order status changed: id=%s %s -> %s",
        order.id,
        previous.value,
        status.value,
    )
    return order


def set_price(db: Session, order: Order, raw_price: str | None) -> Decimal | None:
    """Set (or clear) the agreed price, announcing it in the chat."""
    from app.models import ChatMessage

    price: Decimal | None
    if raw_price is None or not str(raw_price).strip():
        price = None
    else:
        try:
            price = Decimal(str(raw_price).replace(",", ".").replace(" ", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Некорректная цена") from exc
        if price < 0:
            raise ValueError("Цена не может быть отрицательной")
        price = price.quantize(Decimal("0.01"))

    if order.price_final == price:
        return price

    order.price_final = price
    db.add(
        ChatMessage(
            order_id=order.id,
            sender_id=None,
            kind=MessageKind.SYSTEM,
            text=(
                f"Итоговая стоимость согласована: {format_money(price)}"
                if price is not None
                else "Итоговая стоимость сброшена"
            ),
        )
    )
    db.commit()
    db.refresh(order)
    logger.info("Order price set: id=%s price=%s", order.id, price)
    return price
