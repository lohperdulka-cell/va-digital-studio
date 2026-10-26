"""Public reviews page and the review submission form."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.flash import flash
from app.logging_config import get_logger
from app.schemas.reviews import ReviewForm
from app.security.csrf import require_csrf
from app.security.deps import DbSession, OptionalUser
from app.services import reviews as review_service
from app.templating import render

logger = get_logger(__name__)

router = APIRouter(tags=["reviews"], dependencies=[Depends(require_csrf)])


@router.get("/reviews")
def reviews_index(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
):
    return render(
        request,
        "reviews.html",
        {
            "reviews": review_service.list_approved(db),
            "summary": review_service.summary(db),
            "form": {
                "author_name": user.display_name if user else "",
            },
            "errors": {},
        },
    )


@router.post("/reviews")
async def reviews_submit(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
):
    """Store a submission for moderation and thank the visitor.

    A review never appears publicly on submit: an admin approves it first.
    """
    raw = await request.form()
    try:
        payload = ReviewForm(
            author_name=str(raw.get("author_name") or ""),
            author_role=str(raw.get("author_role") or ""),
            rating=_as_int(raw.get("rating")),
            body=str(raw.get("body") or ""),
        )
    except ValidationError as exc:
        errors = _field_errors(exc)
        logger.info("Review rejected: %s", errors)
        return render(
            request,
            "reviews.html",
            {
                "reviews": review_service.list_approved(db),
                "summary": review_service.summary(db),
                "form": {
                    "author_name": str(raw.get("author_name") or ""),
                    "author_role": str(raw.get("author_role") or ""),
                    "rating": _as_int(raw.get("rating")),
                    "body": str(raw.get("body") or ""),
                },
                "errors": errors,
            },
            status_code=422,
        )

    review_service.create_review(
        db,
        author_name=payload.author_name,
        author_role=payload.author_role,
        rating=payload.rating,
        body=payload.body,
        user_id=user.id if user else None,
    )
    flash(
        request,
        "Спасибо за отзыв! Он появится на сайте после проверки модератором.",
        "success",
    )
    return RedirectResponse("/reviews", status_code=303)


def _as_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _field_errors(exc: Exception) -> dict[str, str]:
    errors: dict[str, str] = {}
    labels = {
        "author_name": "Имя",
        "author_role": "Роль или компания",
        "rating": "Оценка",
        "body": "Текст отзыва",
    }
    for error in getattr(exc, "errors", list)():
        field = str(error.get("loc", ("",))[-1])
        errors[field] = f"{labels.get(field, field)}: {error.get('msg', 'некорректное значение')}"
    return errors or {"body": "Не удалось проверить отзыв"}
