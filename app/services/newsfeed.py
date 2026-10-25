"""News feed queries and like toggling."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.logging_config import get_logger
from app.models import News, NewsLike
from app.services.slugs import unique_slug

logger = get_logger(__name__)

PAGE_SIZE = 6


def list_news(
    db: Session, *, limit: int | None = None, offset: int = 0
) -> list[News]:
    """Published news, newest first, with likes eagerly loaded for the counters."""
    statement = (
        select(News)
        .where(News.is_published.is_(True))
        .options(selectinload(News.likes))
        .order_by(News.published_at.desc(), News.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list(db.scalars(statement))


def count_news(db: Session) -> int:
    return int(
        db.scalar(select(func.count(News.id)).where(News.is_published.is_(True))) or 0
    )


def get_news_by_slug(db: Session, slug: str) -> News | None:
    return db.scalar(
        select(News)
        .where(News.slug == slug, News.is_published.is_(True))
        .options(selectinload(News.likes))
    )


def get_news(db: Session, news_id: int) -> News | None:
    return db.scalar(
        select(News).where(News.id == news_id).options(selectinload(News.likes))
    )


def toggle_like(db: Session, *, news_id: int, user_id: int) -> tuple[bool, int]:
    """Add or remove a like. Returns ``(liked, total_likes)``.

    Uniqueness is enforced by the ``uq_news_likes_user_news`` constraint, so a
    double-click cannot create two rows; the IntegrityError path handles the
    race where two requests arrive at once.
    """
    existing = db.scalar(
        select(NewsLike).where(
            NewsLike.news_id == news_id, NewsLike.user_id == user_id
        )
    )

    if existing is not None:
        db.execute(
            delete(NewsLike).where(
                NewsLike.news_id == news_id, NewsLike.user_id == user_id
            )
        )
        liked = False
    else:
        db.add(NewsLike(news_id=news_id, user_id=user_id))
        liked = True
        try:
            db.flush()
        except IntegrityError:
            # Someone else inserted the same like first — treat as liked.
            db.rollback()
            liked = True

    db.commit()
    total = int(
        db.scalar(
            select(func.count(NewsLike.id)).where(NewsLike.news_id == news_id)
        )
        or 0
    )
    logger.info(
        "News like toggled: news_id=%s user_id=%s liked=%s total=%s",
        news_id,
        user_id,
        liked,
        total,
    )
    return liked, total


def liked_news_ids(db: Session, user_id: int | None) -> set[int]:
    """Ids of news the given user has liked, for rendering button state."""
    if user_id is None:
        return set()
    return set(
        db.scalars(select(NewsLike.news_id).where(NewsLike.user_id == user_id))
    )


# --- Admin CRUD ------------------------------------------------------------


def list_all_news(db: Session, *, limit: int = 200) -> list[News]:
    """Every news item including drafts, for the admin table."""
    return list(
        db.scalars(
            select(News)
            .options(selectinload(News.likes))
            .order_by(News.published_at.desc(), News.id.desc())
            .limit(limit)
        )
    )


def create_news(db: Session, data: dict) -> News:
    payload = dict(data)
    payload["slug"] = unique_slug(
        db, News, payload.get("slug") or "", fallback="news"
    )
    item = News(**payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    logger.info("News created: id=%s slug=%s", item.id, item.slug)
    return item


def update_news(db: Session, item: News, data: dict) -> News:
    payload = dict(data)
    desired = payload.pop("slug", "") or item.slug
    payload["slug"] = unique_slug(
        db, News, desired, fallback="news", exclude_id=item.id
    )
    for field, value in payload.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    logger.info("News updated: id=%s slug=%s", item.id, item.slug)
    return item


def delete_news(db: Session, item: News) -> None:
    """Delete an item; likes are removed by the ORM cascade."""
    news_id = item.id
    db.delete(item)
    db.commit()
    logger.info("News deleted: id=%s", news_id)
