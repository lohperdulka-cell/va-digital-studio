"""News pages and the AJAX like endpoint."""

from __future__ import annotations

import math

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.errors import NotFoundError
from app.logging_config import get_logger
from app.security.deps import CurrentUser, DbSession
from app.services import newsfeed as news_service
from app.services.newsfeed import PAGE_SIZE
from app.templating import render

logger = get_logger(__name__)

router = APIRouter(tags=["news"])


@router.get("/news")
def news_index(
    request: Request,
    db: DbSession,
    page: int = Query(default=1, ge=1),
):
    total = news_service.count_news(db)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    items = news_service.list_news(
        db, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )
    return render(
        request,
        "news_list.html",
        {"news": items, "page": page, "total_pages": total_pages, "total": total},
    )


@router.get("/news/{slug}")
def news_detail(
    request: Request,
    slug: str,
    db: DbSession,
):
    item = news_service.get_news_by_slug(db, slug)
    if item is None:
        raise NotFoundError(detail="Новость не найдена")
    return render(request, "news_detail.html", {"item": item})


@router.post("/api/news/{news_id}/like")
def toggle_like(
    news_id: int,
    user: CurrentUser,
    db: DbSession,
):
    """Toggle the current user's like.

    The ``CurrentUser`` dependency makes anonymous callers fail with 401 (JSON,
    because the client sends ``Accept: application/json``), which the frontend
    turns into a redirect to Google.
    """
    if news_service.get_news(db, news_id) is None:
        raise NotFoundError(detail="Новость не найдена")

    liked, total = news_service.toggle_like(db, news_id=news_id, user_id=user.id)
    return JSONResponse({"liked": liked, "likes_count": total, "news_id": news_id})
