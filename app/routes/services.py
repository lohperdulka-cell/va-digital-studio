"""Service catalogue pages."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.errors import NotFoundError
from app.models.enums import ServiceCategory
from app.security.deps import DbSession
from app.services import catalog as catalog_service
from app.templating import render

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _parse_category(raw: str | None) -> ServiceCategory | None:
    """Ignore an unknown ?category= value instead of erroring."""
    if not raw:
        return None
    try:
        return ServiceCategory(raw)
    except ValueError:
        return None


@router.get("")
def catalog(
    request: Request,
    db: DbSession,
    category: str | None = Query(default=None),
):
    active = _parse_category(category)
    services = catalog_service.list_services(db, category=active)
    return render(
        request,
        "catalog.html",
        {
            "services": services,
            "categories": list(ServiceCategory),
            "active_category": active.value if active else None,
            "counts": catalog_service.category_counts(db),
            "total": len(services),
        },
    )


@router.get("/{slug}")
def service_detail(
    request: Request,
    slug: str,
    db: DbSession,
):
    service = catalog_service.get_service_by_slug(db, slug)
    if service is None:
        raise NotFoundError(detail="Услуга не найдена или снята с публикации")
    return render(
        request,
        "service_detail.html",
        {
            "service": service,
            "related": catalog_service.related_services(db, service),
        },
    )
