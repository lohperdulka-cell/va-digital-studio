"""Client reviews: submission, moderation and public listing."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Review
from app.models.review import MAX_RATING, MIN_RATING

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReviewSummary:
    """Aggregate rating shown above the review list."""

    count: int
    average: float

    @property
    def average_display(self) -> str:
        return f"{self.average:.1f}"


def list_approved(db: Session, *, limit: int | None = None) -> list[Review]:
    statement = (
        select(Review)
        .where(Review.is_approved.is_(True))
        .order_by(Review.created_at.desc(), Review.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(db.scalars(statement))


def summary(db: Session) -> ReviewSummary:
    """Average rating and count over approved reviews only."""
    row = db.execute(
        select(func.count(Review.id), func.avg(Review.rating)).where(
            Review.is_approved.is_(True)
        )
    ).one()
    count, average = row
    return ReviewSummary(count=int(count or 0), average=float(average or 0.0))


def list_pending(db: Session, *, limit: int = 200) -> list[Review]:
    """Reviews awaiting moderation, oldest first so nothing is forgotten."""
    return list(
        db.scalars(
            select(Review)
            .where(Review.is_approved.is_(False))
            .order_by(Review.created_at.asc(), Review.id.asc())
            .limit(limit)
        )
    )


def list_all(db: Session, *, limit: int = 200) -> list[Review]:
    return list(
        db.scalars(
            select(Review).order_by(Review.created_at.desc(), Review.id.desc()).limit(limit)
        )
    )


def get_review(db: Session, review_id: int) -> Review | None:
    return db.get(Review, review_id)


def create_review(
    db: Session,
    *,
    author_name: str,
    author_role: str,
    rating: int,
    body: str,
    user_id: int | None = None,
) -> Review:
    """Store a submission as unapproved; it goes live after moderation."""
    clamped = max(MIN_RATING, min(MAX_RATING, int(rating)))
    review = Review(
        user_id=user_id,
        author_name=author_name,
        author_role=author_role,
        rating=clamped,
        body=body,
        is_approved=False,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    logger.info("Review submitted: id=%s user_id=%s", review.id, user_id)
    return review


def approve(db: Session, review: Review) -> Review:
    review.is_approved = True
    db.commit()
    db.refresh(review)
    logger.info("Review approved: id=%s", review.id)
    return review


def reject(db: Session, review: Review) -> None:
    """Rejecting deletes the row: an unapproved review has no archival value."""
    review_id = review.id
    db.delete(review)
    db.commit()
    logger.info("Review rejected and removed: id=%s", review_id)
