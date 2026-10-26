"""Pydantic schemas: validation for every value a user can submit.

Forms arrive as raw strings from ``application/x-www-form-urlencoded`` bodies,
so the models below coerce and normalise them: money strings such as
``"25 000"`` become :class:`~decimal.Decimal`, comma-separated tags become a
de-duplicated list, and free text is sanitised before it can ever reach a
template.  Anything that fails validation raises ``pydantic.ValidationError``,
which the route handlers turn into a flash message or a 422 response.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import ServiceCategory
from app.security.sanitize import clean_plain_text, clean_rich_text

# Chat messages are the shortest-lived, highest-frequency content on the site,
# so the cap is tighter than the support form's.  Exported because the service
# layer enforces the same bound when it truncates before storage.
CHAT_MESSAGE_MAX = 2000

# Shared bounds, mirrored by the ``minlength``/``maxlength`` attributes in the
# templates.  Keeping them in one place stops the client and server disagreeing.
_SUBJECT_MIN = 3
_SUBJECT_MAX = 200
_MESSAGE_MIN = 10
_MESSAGE_MAX = 5000
_REPLY_MIN = 3
_TITLE_MIN = 3
_RICH_TEXT_MAX = 20000

# A decimal number with either separator and optional grouping spaces.  The
# non-breaking space is included because browsers and pasted spreadsheets use
# it as a thousands separator.
_MONEY_CLEAN = re.compile(r"[^\d,.\-]")


def _parse_money(value: object) -> Decimal:
    """Turn ``"25 000"``, ``"25,5"`` or ``25000`` into a :class:`Decimal`."""
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    text = _MONEY_CLEAN.sub("", str(value)).replace(",", ".")
    if not text or text in {"-", ".", "-."}:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError("Некорректная цена") from exc


def _split_tags(value: object) -> list[str]:
    """Parse ``"n8n, интеграции, n8n"`` into ``["n8n", "интеграции"]``.

    Order is preserved and duplicates are dropped so the chips in the catalogue
    do not repeat.
    """
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        raw_items = [str(item) for item in value]
    else:
        raw_items = str(value).split(",")

    tags: list[str] = []
    for item in raw_items:
        tag = clean_plain_text(item, max_length=60)
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:20]


# --- Public forms ----------------------------------------------------------


class SupportTicketForm(BaseModel):
    """Enquiry from the contact page, the /support page or the footer modal."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subject: str = Field(min_length=_SUBJECT_MIN, max_length=_SUBJECT_MAX)
    message: str = Field(min_length=_MESSAGE_MIN, max_length=_MESSAGE_MAX)
    # Optional: a signed-in visitor's address fills the gap, and the contact
    # form lets an anonymous visitor leave it blank.
    email: EmailStr | None = None
    name: str = Field(default="", max_length=200)

    @field_validator("subject", "message")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plain_text(value, max_length=_MESSAGE_MAX)


class ChatMessageIn(BaseModel):
    """One frame from the order chat WebSocket."""

    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=CHAT_MESSAGE_MAX)

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plain_text(value, max_length=CHAT_MESSAGE_MAX)


class TicketReplyForm(BaseModel):
    """A staff answer to a support ticket."""

    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=_REPLY_MIN, max_length=_MESSAGE_MAX)

    @field_validator("body")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plain_text(value, max_length=_MESSAGE_MAX)


# --- Admin forms -----------------------------------------------------------


class ServiceForm(BaseModel):
    """Create/update a catalogue service from the dashboard form."""

    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(default="", max_length=120)
    title: str = Field(min_length=_TITLE_MIN, max_length=200)
    short_description: str = Field(default="", max_length=400)
    description: str = Field(default="", max_length=_RICH_TEXT_MAX)
    category: ServiceCategory = ServiceCategory.SITES
    tags: list[str] = Field(default_factory=list)
    price_from: Decimal = Decimal("0")
    duration_days: int = Field(default=14, ge=0, le=3650)
    icon: str = Field(default="🚀", max_length=8)
    is_active: bool = True
    is_featured: bool = False
    sort_order: int = Field(default=0, ge=0, le=9999)

    @field_validator("title", "short_description")
    @classmethod
    def _clean_plain(cls, value: str) -> str:
        return clean_plain_text(value, max_length=400)

    @field_validator("description")
    @classmethod
    def _clean_rich(cls, value: str) -> str:
        return clean_rich_text(value)

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, value: object) -> list[str]:
        return _split_tags(value)

    @field_validator("price_from", mode="before")
    @classmethod
    def _parse_price(cls, value: object) -> Decimal:
        return _parse_money(value)


class NewsForm(BaseModel):
    """Create/update a news item from the dashboard form."""

    model_config = ConfigDict(str_strip_whitespace=True)

    slug: str = Field(default="", max_length=160)
    title: str = Field(min_length=_TITLE_MIN, max_length=240)
    preview: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=_RICH_TEXT_MAX)
    cover_emoji: str = Field(default="📰", max_length=8)
    is_published: bool = True

    @field_validator("title", "preview")
    @classmethod
    def _clean_plain(cls, value: str) -> str:
        return clean_plain_text(value, max_length=500)

    @field_validator("body")
    @classmethod
    def _clean_rich(cls, value: str) -> str:
        return clean_rich_text(value)
