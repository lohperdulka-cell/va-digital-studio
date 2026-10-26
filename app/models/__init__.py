"""ORM models.  Importing this package registers every table on ``Base.metadata``."""

from app.models.chat import ChatMessage, presence
from app.models.enums import (
    MessageKind,
    OrderStatus,
    ServiceCategory,
    TicketStatus,
)
from app.models.login_code import LoginCode
from app.models.news import News, NewsLike
from app.models.order import Order
from app.models.service import Service
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User

__all__ = [
    "ChatMessage",
    "LoginCode",
    "MessageKind",
    "News",
    "NewsLike",
    "Order",
    "OrderStatus",
    "Service",
    "ServiceCategory",
    "SupportMessage",
    "SupportTicket",
    "TicketStatus",
    "User",
    "presence",
]
