"""Portfolio queries: published cases for the public site and the admin table."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Case
from app.services.slugs import unique_slug

logger = get_logger(__name__)


def list_cases(
    db: Session, *, limit: int | None = None, offset: int = 0
) -> list[Case]:
    """Published cases, featured first, then by manual order and recency."""
    statement = (
        select(Case)
        .where(Case.is_published.is_(True))
        .order_by(
            Case.is_featured.desc(),
            Case.sort_order.asc(),
            Case.published_at.desc(),
            Case.id.desc(),
        )
    )
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list(db.scalars(statement))


def count_cases(db: Session) -> int:
    return int(
        db.scalar(select(func.count(Case.id)).where(Case.is_published.is_(True))) or 0
    )


def get_case_by_slug(db: Session, slug: str) -> Case | None:
    return db.scalar(
        select(Case).where(Case.slug == slug, Case.is_published.is_(True))
    )


def list_all_cases(db: Session, *, limit: int = 200) -> list[Case]:
    """Every case including drafts, for the admin table."""
    return list(
        db.scalars(
            select(Case)
            .order_by(Case.sort_order.asc(), Case.published_at.desc(), Case.id.desc())
            .limit(limit)
        )
    )


def get_case(db: Session, case_id: int) -> Case | None:
    return db.get(Case, case_id)


def create_case(db: Session, data: dict) -> Case:
    payload = dict(data)
    payload["slug"] = unique_slug(
        db, Case, payload.get("slug") or "", fallback="case"
    )
    case = Case(**payload)
    db.add(case)
    db.commit()
    db.refresh(case)
    logger.info("Case created: id=%s slug=%s", case.id, case.slug)
    return case


def update_case(db: Session, case: Case, data: dict) -> Case:
    payload = dict(data)
    desired = payload.pop("slug", "") or case.slug
    payload["slug"] = unique_slug(
        db, Case, desired, fallback="case", exclude_id=case.id
    )
    for field, value in payload.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    logger.info("Case updated: id=%s slug=%s", case.id, case.slug)
    return case


def delete_case(db: Session, case: Case) -> None:
    case_id = case.id
    db.delete(case)
    db.commit()
    logger.info("Case deleted: id=%s", case_id)
