"""Pydantic schemas: validation for every value a user can submit.

Public names are re-exported here so route modules can simply do
``from app.schemas import SupportTicketForm``.
"""

from __future__ import annotations

from app.schemas.forms import (
    CHAT_MESSAGE_MAX,
    ChatMessageIn,
    NewsForm,
    ServiceForm,
    SupportTicketForm,
    TicketReplyForm,
)

__all__ = [
    "CHAT_MESSAGE_MAX",
    "ChatMessageIn",
    "NewsForm",
    "ServiceForm",
    "SupportTicketForm",
    "TicketReplyForm",
]
