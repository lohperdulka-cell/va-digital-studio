"""Catalogue queries: services and their categories."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Order, Service
from app.models.enums import OrderStatus, ServiceCategory
from app.services.slugs import unique_slug

logger = get_logger(__name__)


@dataclass(frozen=True)
class HomeStats:
    """Headline numbers for the hero section."""

    services: int
    orders: int
    days: int


def list_services(
    db: Session, *, category: ServiceCategory | None = None, limit: int | None = None
) -> list[Service]:
    """Active services, featured first, then by manual sort order."""
    statement = select(Service).where(Service.is_active.is_(True))
    if category is not None:
        statement = statement.where(Service.category == category)
    statement = statement.order_by(
        Service.is_featured.desc(), Service.sort_order.asc(), Service.id.asc()
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement))


def list_all_services(db: Session) -> list[Service]:
    """Every service including inactive ones, for the admin catalogue table."""
    return list(
        db.scalars(
            select(Service).order_by(
                Service.sort_order.asc(), Service.id.asc()
            )
        )
    )


def get_service_by_slug(db: Session, slug: str) -> Service | None:
    return db.scalar(
        select(Service).where(Service.slug == slug, Service.is_active.is_(True))
    )


def get_service(db: Session, service_id: int) -> Service | None:
    return db.get(Service, service_id)


def related_services(
    db: Session, service: Service, *, limit: int = 3
) -> list[Service]:
    """Other active services in the same category."""
    statement = (
        select(Service)
        .where(
            Service.is_active.is_(True),
            Service.category == service.category,
            Service.id != service.id,
        )
        .order_by(Service.sort_order.asc(), Service.id.asc())
        .limit(limit)
    )
    return list(db.scalars(statement))


def category_counts(db: Session) -> dict[str, int]:
    """Number of active services per category, for the filter pills."""
    statement = (
        select(Service.category, func.count(Service.id))
        .where(Service.is_active.is_(True))
        .group_by(Service.category)
    )
    return {
        (category.value if hasattr(category, "value") else str(category)): count
        for category, count in db.execute(statement)
    }


def home_stats(db: Session) -> HomeStats:
    """Hero counters derived from real data rather than hard-coded numbers."""
    service_count = db.scalar(
        select(func.count(Service.id)).where(Service.is_active.is_(True))
    )
    order_count = db.scalar(
        select(func.count(Order.id)).where(Order.status != OrderStatus.CANCELLED)
    )
    average_days = db.scalar(
        select(func.avg(Service.duration_days)).where(Service.is_active.is_(True))
    )
    return HomeStats(
        services=int(service_count or 0),
        orders=int(order_count or 0),
        days=round(float(average_days)) if average_days else 0,
    )


# --- Admin CRUD ------------------------------------------------------------


def create_service(db: Session, data: dict) -> Service:
    payload = dict(data)
    payload["slug"] = unique_slug(
        db, Service, payload.get("slug") or "", fallback="service"
    )
    service = Service(**payload)
    db.add(service)
    db.commit()
    db.refresh(service)
    logger.info("Service created: id=%s slug=%s", service.id, service.slug)
    return service


def update_service(db: Session, service: Service, data: dict) -> Service:
    payload = dict(data)
    desired = payload.pop("slug", "") or service.slug
    payload["slug"] = unique_slug(
        db, Service, desired, fallback="service", exclude_id=service.id
    )
    for field, value in payload.items():
        setattr(service, field, value)
    db.commit()
    db.refresh(service)
    logger.info("Service updated: id=%s slug=%s", service.id, service.slug)
    return service


def delete_service(db: Session, service: Service) -> None:
    """Remove a service. Orders keep their history via ``ondelete=SET NULL``."""
    service_id = service.id
    db.delete(service)
    db.commit()
    logger.info("Service deleted: id=%s", service_id)
