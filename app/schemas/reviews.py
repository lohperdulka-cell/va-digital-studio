"""Form schemas for the review and calculator pages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.review import MAX_RATING, MIN_RATING
from app.security.sanitize import clean_plain_text

_NAME_MIN = 2
_NAME_MAX = 120
_ROLE_MAX = 160
_BODY_MIN = 20
_BODY_MAX = 1500


class ReviewForm(BaseModel):
    """A public review submission.

    Everything is sanitised here so the stored row is already safe; moderation
    only decides whether it is shown, not whether it is safe to store.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    author_name: str = Field(min_length=_NAME_MIN, max_length=_NAME_MAX)
    author_role: str = Field(default="", max_length=_ROLE_MAX)
    rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    body: str = Field(min_length=_BODY_MIN, max_length=_BODY_MAX)

    @field_validator("author_name", "author_role", "body")
    @classmethod
    def _clean(cls, value: str) -> str:
        return clean_plain_text(value)


class CalculatorForm(BaseModel):
    """Answers from the cost calculator.

    The values are validated against the known keys by the service layer, which
    falls back to defaults, so this only needs to keep them well-typed.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    project_type: str = Field(default="landing", max_length=32)
    scope: str = Field(default="standard", max_length=32)
    deadline: str = Field(default="normal", max_length=32)
    addons: list[str] = Field(default_factory=list)
