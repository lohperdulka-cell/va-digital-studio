"""Enumerations shared by ORM models and Pydantic schemas."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum: serialises cleanly and stores as VARCHAR."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class ServiceCategory(StrEnum):
    SITES = "sites"
    BOTS = "bots"
    AUTOMATION = "automation"
    DESIGN = "design"

    @property
    def label(self) -> str:
        return _CATEGORY_LABELS[self]


_CATEGORY_LABELS = {
    ServiceCategory.SITES: "Сайты",
    ServiceCategory.BOTS: "Telegram-боты",
    ServiceCategory.AUTOMATION: "Автоматизация",
    ServiceCategory.DESIGN: "Дизайн",
}


class OrderStatus(StrEnum):
    DRAFT = "draft"
    DISCUSSING = "discussing"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return _ORDER_STATUS_LABELS[self]

    @property
    def css_class(self) -> str:
        return _ORDER_STATUS_CSS[self]

    @property
    def is_terminal(self) -> bool:
        return self in {OrderStatus.DONE, OrderStatus.CANCELLED}


_ORDER_STATUS_LABELS = {
    OrderStatus.DRAFT: "Черновик",
    OrderStatus.DISCUSSING: "Обсуждение",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.REVIEW: "На проверке",
    OrderStatus.DONE: "Завершён",
    OrderStatus.CANCELLED: "Отменён",
}

_ORDER_STATUS_CSS = {
    OrderStatus.DRAFT: "status-draft",
    OrderStatus.DISCUSSING: "status-discussing",
    OrderStatus.IN_PROGRESS: "status-progress",
    OrderStatus.REVIEW: "status-review",
    OrderStatus.DONE: "status-done",
    OrderStatus.CANCELLED: "status-cancelled",
}


class TicketStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"

    @property
    def label(self) -> str:
        return "Открыт" if self is TicketStatus.OPEN else "Закрыт"

    @property
    def css_class(self) -> str:
        return "status-review" if self is TicketStatus.OPEN else "status-done"


class MessageKind(StrEnum):
    """Distinguishes the two parties in an order chat."""

    CLIENT = "client"
    STAFF = "staff"
    SYSTEM = "system"
