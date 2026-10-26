"""Public portfolio pages: the list and a single case."""

from __future__ import annotations

import math

from fastapi import APIRouter, Query, Request

from app.errors import NotFoundError
from app.security.deps import DbSession
from app.services import portfolio as portfolio_service
from app.templating import render

router = APIRouter(tags=["portfolio"])

PAGE_SIZE = 9


@router.get("/portfolio")
def portfolio_index(
    request: Request,
    db: DbSession,
    page: int = Query(default=1, ge=1),
):
    total = portfolio_service.count_cases(db)
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    cases = portfolio_service.list_cases(
        db, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )
    return render(
        request,
        "portfolio_list.html",
        {"cases": cases, "page": page, "total_pages": total_pages, "total": total},
    )


@router.get("/portfolio/{slug}")
def portfolio_detail(request: Request, slug: str, db: DbSession):
    case = portfolio_service.get_case_by_slug(db, slug)
    if case is None:
        raise NotFoundError(detail="Кейс не найден")
    return render(request, "portfolio_detail.html", {"case": case})
