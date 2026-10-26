"""Reviews: submission, moderation and the public page."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.security.csrf import CSRF_COOKIE_NAME
from app.services import reviews as review_service


def _csrf(client: TestClient) -> str:
    """Fetch a page so the double-submit cookie exists, then read it."""
    client.get("/")
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token, "CSRF cookie was not issued"
    return token


def _submit(client, **overrides):
    data = {
        "author_name": "Иван П.",
        "author_role": "Клиент",
        "rating": "5",
        "body": "Отличная работа, всё сделали быстро и качественно.",
        "csrf_token": _csrf(client),
    }
    data.update(overrides)
    return client.post("/reviews", data=data, follow_redirects=False)


def test_submitted_review_is_pending_not_public(db, client):
    response = _submit(client)
    assert response.status_code == 303

    pending = review_service.list_pending(db)
    assert len(pending) == 1
    assert pending[0].is_approved is False
    assert review_service.list_approved(db) == []


def test_approve_publishes_the_review(db, client):
    _submit(client)
    review = review_service.list_pending(db)[0]
    review_service.approve(db, review)
    assert len(review_service.list_approved(db)) == 1


def test_reject_deletes_the_review(db, client):
    _submit(client)
    review = review_service.list_pending(db)[0]
    review_service.reject(db, review)
    assert review_service.list_pending(db) == []


def test_rating_is_clamped_by_the_service(db):
    review = review_service.create_review(
        db, author_name="Тест", author_role="", rating=99, body="Длинный текст отзыва"
    )
    assert review.rating == 5


def test_summary_counts_only_approved(db, client):
    _submit(client)
    assert review_service.summary(db).count == 0

    review = review_service.list_pending(db)[0]
    review_service.approve(db, review)
    summary = review_service.summary(db)
    assert summary.count == 1
    assert summary.average == 5.0


def test_short_body_is_rejected(client):
    response = _submit(client, body="мало")
    assert response.status_code == 422


def test_reviews_page_shows_approved_ones(client, db):
    review = review_service.create_review(
        db, author_name="Пётр", author_role="", rating=4, body="Хороший проект, рекомендую."
    )
    review_service.approve(db, review)

    page = client.get("/reviews")
    assert page.status_code == 200
    assert "Пётр" in page.text
