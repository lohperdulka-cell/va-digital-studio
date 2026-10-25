"""URL-slug allocation shared by the catalogue and news admin forms.

Slugs are user-editable, so two editors can easily type the same one. Rather
than failing the save, a free variant is derived by appending a counter — the
unique index on the column stays the final authority, this just avoids the
IntegrityError reaching the user.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

# Safety valve: a pathological loop of taken slugs should error, not hang.
_MAX_ATTEMPTS = 500


def slug_taken(
    db: Session,
    model: type[Any],
    slug: str,
    *,
    exclude_id: int | None = None,
) -> bool:
    """Whether ``model`` already has a row with this slug."""
    statement = select(model.id).where(model.slug == slug)
    if exclude_id is not None:
        statement = statement.where(model.id != exclude_id)
    return db.scalar(statement) is not None


def unique_slug(
    db: Session,
    model: type[Any],
    base: str,
    *,
    fallback: str,
    exclude_id: int | None = None,
) -> str:
    """Return ``base`` if free, otherwise ``base-2``, ``base-3``, …

    ``fallback`` is used when ``base`` is empty (e.g. a title made entirely of
    characters the slugifier strips).
    """
    candidate = base or fallback
    if not slug_taken(db, model, candidate, exclude_id=exclude_id):
        return candidate
    for suffix in range(2, _MAX_ATTEMPTS):
        attempt = f"{candidate}-{suffix}"
        if not slug_taken(db, model, attempt, exclude_id=exclude_id):
            return attempt
    raise RuntimeError(f"Не удалось подобрать свободный slug для {candidate!r}")
