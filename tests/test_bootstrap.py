"""Startup bootstrap: empty-catalogue seeding and ADMIN_EMAILS promotion.

These cover the two problems a card-free host creates: there is no Shell to run
``python -m app.seed`` in, and no way to promote the first administrator by hand.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models import Case, News, Review, Service
from app.models.enums import ServiceCategory
from app.seed import (
    bootstrap,
    promote_admins,
    seed_cases,
    seed_news,
    seed_reviews,
    seed_services,
)
from app.services.accounts import register_with_password, upsert_user


def _profile(email: str) -> dict[str, str | None]:
    return {
        "google_id": f"google-{email}",
        "email": email,
        "name": "Тест",
        "avatar_url": None,
    }


# --- Seeding -----------------------------------------------------------------


def test_seed_services_creates_the_full_catalogue(db):
    created, updated = seed_services(db)
    assert created == 4
    assert updated == 0

    services = db.scalars(select(Service).order_by(Service.sort_order)).all()
    assert [s.slug for s in services] == [
        "landing-page",
        "multipage-site",
        "telegram-bot-orders",
        "automation-script",
    ]
    assert all(Decimal("500") <= s.price_from <= Decimal("5000") for s in services)


def test_seed_services_is_idempotent(db):
    seed_services(db)
    created, updated = seed_services(db)
    assert created == 0
    assert updated == 4
    assert db.scalar(select(Service).order_by(Service.id)) is not None
    assert len(db.scalars(select(Service)).all()) == 4


def test_seed_news_is_idempotent(db):
    seed_news(db)
    created, updated = seed_news(db)
    assert created == 0
    assert updated == 4
    assert len(db.scalars(select(News)).all()) == 4


def test_bootstrap_fills_an_empty_catalogue(db):
    bootstrap()
    assert len(db.scalars(select(Service)).all()) == 4
    assert len(db.scalars(select(News)).all()) == 4


def test_bootstrap_skips_a_populated_catalogue(db):
    db.add(
        Service(
            slug="handmade",
            title="Ручная услуга",
            category=ServiceCategory.SITES,
            price_from=Decimal("999.00"),
        )
    )
    db.commit()

    bootstrap()

    services = db.scalars(select(Service)).all()
    assert len(services) == 1
    assert services[0].slug == "handmade"


def test_bootstrap_does_not_overwrite_dashboard_edits(db):
    bootstrap()
    service = db.scalar(select(Service).where(Service.slug == "landing-page"))
    service.title = "Отредактировано в дашборде"
    db.commit()

    bootstrap()

    db.expire_all()
    service = db.scalar(select(Service).where(Service.slug == "landing-page"))
    assert service.title == "Отредактировано в дашборде"


def test_seed_cases_and_reviews(db):
    created, _ = seed_cases(db)
    assert created == 3
    reviews_created = seed_reviews(db)
    assert reviews_created == 3
    assert len(db.scalars(select(Case)).all()) == 3
    assert len(db.scalars(select(Review)).all()) == 3


def test_seed_reviews_is_idempotent(db):
    seed_reviews(db)
    assert seed_reviews(db) == 0
    assert len(db.scalars(select(Review)).all()) == 3


def test_bootstrap_adds_cases_and_reviews_to_an_existing_site(db):
    """A redeploy on a populated catalogue still gains the new sections."""
    bootstrap()
    assert len(db.scalars(select(Case)).all()) == 3
    assert len(db.scalars(select(Review)).all()) == 3

    bootstrap()
    assert len(db.scalars(select(Case)).all()) == 3
    assert len(db.scalars(select(Review)).all()) == 3


# --- Admin promotion ---------------------------------------------------------


def test_bootstrap_promotes_an_existing_user(db, make_user):
    user = make_user("boss@example.com", is_admin=False)

    bootstrap()

    db.refresh(user)
    assert user.is_admin is True


def test_bootstrap_promotes_when_admin_emails_was_pasted_dirty(db, make_user, monkeypatch):
    """A quoted or non-breaking-space value must not silently skip promotion."""
    monkeypatch.setattr(settings, "admin_emails", ' "boss@example.com"\u00a0 ')
    user = make_user("boss@example.com", is_admin=False)

    bootstrap()

    db.refresh(user)
    assert user.is_admin is True


def test_bootstrap_leaves_other_users_alone(db, make_user):
    user = make_user("someone@example.com", is_admin=False)

    bootstrap()

    db.refresh(user)
    assert user.is_admin is False


def test_upsert_user_grants_admin_on_first_login(db):
    user, created = upsert_user(db, _profile("boss@example.com"))
    assert created is True
    assert user.is_admin is True


def test_upsert_user_leaves_a_regular_user_alone(db):
    user, _ = upsert_user(db, _profile("regular@example.com"))
    assert user.is_admin is False


def test_middleware_self_heals_admin_rights(client, db, make_user, login_as):
    """An account created before ADMIN_EMAILS was set still gains access."""
    user = make_user("boss@example.com", is_admin=False)
    login_as(user)

    body = client.get("/dashboard").text

    assert "/dashboard" in body
    db.refresh(user)
    assert user.is_admin is True


def test_middleware_does_not_promote_a_regular_user(client, db, make_user, login_as):
    user = make_user("regular@example.com", is_admin=False)
    login_as(user)

    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 403
    db.refresh(user)
    assert user.is_admin is False


# --- Owner fallback when ADMIN_EMAILS is unset -------------------------------


def test_first_account_becomes_owner_without_admin_emails(db, monkeypatch):
    """A card-free host has no Shell: the first account must own the site.

    ``ADMIN_EMAILS`` is empty here on purpose — this is the deployed state that
    left the dashboard unreachable.
    """
    monkeypatch.setattr(settings, "admin_emails", "")

    owner = register_with_password(
        db, email="owner@example.com", password="secret123", username="owner"
    )

    assert owner.is_admin is True


def test_a_later_account_does_not_become_owner(db, monkeypatch):
    """Only the first account gets the fallback; the second stays a visitor."""
    monkeypatch.setattr(settings, "admin_emails", "")

    register_with_password(
        db, email="owner@example.com", password="secret123", username="owner"
    )
    visitor = register_with_password(
        db, email="visitor@example.com", password="secret123", username="visitor"
    )

    assert visitor.is_admin is False


def test_existing_owner_is_promoted_by_bootstrap(db, monkeypatch):
    """An account created before the fallback existed gains access on deploy."""
    monkeypatch.setattr(settings, "admin_emails", "")
    from app.models import User

    db.add(User(email="first@example.com", name="Первый"))
    db.add(User(email="second@example.com", name="Второй"))
    db.commit()

    changed = promote_admins(db)

    assert changed == 1
    first = db.scalar(select(User).where(User.email == "first@example.com"))
    second = db.scalar(select(User).where(User.email == "second@example.com"))
    assert first.is_admin is True
    assert second.is_admin is False


def test_admin_emails_still_wins_over_the_fallback(db, monkeypatch):
    """An explicit list is authoritative: it is not the oldest account that wins."""
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    from app.models import User

    db.add(User(email="oldest@example.com", name="Старейший"))
    db.commit()

    promote_admins(db)

    oldest = db.scalar(select(User).where(User.email == "oldest@example.com"))
    boss = db.scalar(select(User).where(User.email == "boss@example.com"))
    assert boss is None or boss.is_admin is False
    assert oldest.is_admin is False


def test_owner_fallback_does_not_override_a_listed_admin(db, monkeypatch):
    """With a list set, membership decides — the oldest account is not special."""
    monkeypatch.setattr(settings, "admin_emails", "boss@example.com")
    from app.models import User

    db.add(User(email="oldest@example.com", name="Старейший"))
    db.add(User(email="boss@example.com", name="Босс"))
    db.commit()

    promote_admins(db)

    oldest = db.scalar(select(User).where(User.email == "oldest@example.com"))
    boss = db.scalar(select(User).where(User.email == "boss@example.com"))
    assert boss.is_admin is True
    assert oldest.is_admin is False
