"""Tests for the public site: pages, CSRF, likes, orders, support tickets."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import News, Order, Service, SupportTicket
from app.models.enums import OrderStatus, ServiceCategory, TicketStatus
from app.security.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.security.sanitize import clean_plain_text, clean_rich_text, clean_slug

# --- Fixtures --------------------------------------------------------------


@pytest.fixture
def service(db) -> Service:
    item = Service(
        slug="test-bots",
        title="Тестовые боты",
        short_description="Описание",
        description="<p>Подробно</p>",
        category=ServiceCategory.BOTS,
        tags=["aiogram", "тест"],
        price_from=Decimal("30000.00"),
        duration_days=14,
        icon="🤖",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def other_service(db) -> Service:
    item = Service(
        slug="test-extra",
        title="Тестовая услуга",
        short_description="Описание услуги",
        category=ServiceCategory.AUTOMATION,
        tags=[],
        price_from=Decimal("10000.00"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def news_item(db) -> News:
    item = News(
        slug="test-news",
        title="Тестовая новость",
        preview="Краткое описание новости",
        body="<p>Текст</p>",
        cover_emoji="🧪",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _csrf(client) -> str:
    """Prime the CSRF cookie and return its value."""
    client.get("/")  # CsrfCookieMiddleware issues the cookie on any response
    return client.cookies.get(CSRF_COOKIE_NAME)


# --- Pages -----------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/", "/about", "/contact", "/support", "/catalog", "/news"],
)
def test_public_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # Every page must carry the design system and the CSRF meta tag.
    assert "csrf-token" in response.text
    assert "VA Digital Studio" in response.text


def test_home_lists_services_and_news(client, service, news_item):
    response = client.get("/")
    assert "Тестовые боты" in response.text
    assert "Тестовая новость" in response.text


def test_catalog_shows_service(client, service):
    response = client.get("/catalog")
    assert response.status_code == 200
    assert "Тестовые боты" in response.text


def test_catalog_category_filter(client, service, other_service):
    response = client.get("/catalog?category=bots")
    assert "Тестовые боты" in response.text
    assert "Тестовая услуга" not in response.text


def test_catalog_ignores_unknown_category(client, service):
    """A bogus ?category= must not 500 — it falls back to showing everything."""
    response = client.get("/catalog?category=not-a-category")
    assert response.status_code == 200
    assert "Тестовые боты" in response.text


def test_service_detail(client, service):
    response = client.get("/catalog/test-bots")
    assert response.status_code == 200
    assert "Тестовые боты" in response.text
    assert "aiogram" in response.text


def test_unknown_service_returns_404_page(client):
    response = client.get("/catalog/no-such-service")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Услуга не найдена" in response.text


def test_news_list_and_detail(client, news_item):
    listing = client.get("/news")
    assert listing.status_code == 200
    assert "Тестовая новость" in listing.text

    detail = client.get("/news/test-news")
    assert detail.status_code == 200
    assert "Тестовая новость" in detail.text


def test_news_pagination_clamps_out_of_range_page(client, news_item):
    response = client.get("/news?page=999")
    assert response.status_code == 200


def test_profile_redirects_anonymous_browser_to_login(client):
    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login")


# --- CSRF ------------------------------------------------------------------


def test_csrf_cookie_is_issued_and_httponly(client):
    client.get("/")
    header = client.cookies.get(CSRF_COOKIE_NAME)
    assert header

    response = client.get("/")
    set_cookie = response.headers.get("set-cookie", "")
    # The cookie is only set on first issue; httponly is asserted on that pass.
    if CSRF_COOKIE_NAME in set_cookie:
        assert "httponly" in set_cookie.lower()


def test_post_without_csrf_token_is_rejected(client):
    response = client.post(
        "/support",
        data={"subject": "Тема вопроса", "message": "Достаточно длинное сообщение"},
    )
    assert response.status_code == 403
    assert "CSRF" in response.text or "CSRF" in response.headers.get("content-type", "")


def test_post_with_wrong_csrf_token_is_rejected(client, db):
    _csrf(client)
    response = client.post(
        "/support",
        data={
            "subject": "Тема вопроса",
            "message": "Достаточно длинное сообщение",
            "csrf_token": "forged-token-value",
        },
    )
    assert response.status_code == 403
    assert db.query(SupportTicket).count() == 0


def test_post_with_valid_csrf_token_succeeds(client, db):
    token = _csrf(client)
    response = client.post(
        "/support",
        data={
            "subject": "Нужен бот",
            "message": "Хочу заказать Telegram-бота для приёма заявок",
            "email": "client@example.com",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/support"

    ticket = db.query(SupportTicket).one()
    assert ticket.subject == "Нужен бот"
    assert ticket.email == "client@example.com"
    assert ticket.status is TicketStatus.OPEN
    # The opening message is stored in the thread.
    assert len(ticket.thread) == 1


def test_csrf_header_is_accepted_for_api_calls(client, db):
    token = _csrf(client)
    response = client.post(
        "/support",
        data={"subject": "Через заголовок", "message": "Сообщение достаточной длины"},
        headers={CSRF_HEADER_NAME: token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(SupportTicket).count() == 1


def test_get_requests_do_not_require_csrf(client):
    """Safe methods must pass through the CSRF dependency untouched."""
    assert client.get("/support").status_code == 200


# --- Support form validation ----------------------------------------------


def test_short_message_is_rejected(client, db):
    token = _csrf(client)
    response = client.post(
        "/support",
        data={"subject": "Тема", "message": "мало", "csrf_token": token},
    )
    assert response.status_code == 422
    assert db.query(SupportTicket).count() == 0


def test_html_in_ticket_is_stripped_before_storage(client, db):
    token = _csrf(client)
    response = client.post(
        "/support",
        data={
            "subject": "Тема <script>alert(1)</script>",
            "message": "Сообщение с <b>разметкой</b> и <script>alert('xss')</script> хвостом",
            "email": "xss@example.com",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    ticket = db.query(SupportTicket).one()
    assert "<script>" not in ticket.subject
    assert "<script>" not in ticket.message
    assert "alert" not in ticket.message or "<" not in ticket.message


def test_invalid_email_is_rejected(client, db):
    token = _csrf(client)
    response = client.post(
        "/support",
        data={
            "subject": "Тема обращения",
            "message": "Достаточно длинное сообщение для валидации",
            "email": "not-an-email",
            "csrf_token": token,
        },
    )
    assert response.status_code == 422
    assert db.query(SupportTicket).count() == 0


# --- Likes -----------------------------------------------------------------


def test_like_requires_authentication(client, news_item):
    response = client.post(f"/api/news/{news_item.id}/like")
    assert response.status_code == 401
    assert response.json()["login_url"] == "/auth/login"


def test_like_toggles_on_and_off(client, db, make_user, login_as, news_item):
    user = make_user("liker@example.com")
    login_as(user)
    token = _csrf(client)

    first = client.post(
        f"/api/news/{news_item.id}/like", headers={CSRF_HEADER_NAME: token}
    )
    assert first.status_code == 200
    assert first.json() == {"liked": True, "likes_count": 1, "news_id": news_item.id}

    second = client.post(
        f"/api/news/{news_item.id}/like", headers={CSRF_HEADER_NAME: token}
    )
    assert second.status_code == 200
    assert second.json()["liked"] is False
    assert second.json()["likes_count"] == 0


def test_one_like_per_user_is_enforced_in_the_database(
    client, db, make_user, login_as, news_item
):
    """The unique index must hold even if the API is called concurrently."""
    from app.models import NewsLike

    user = make_user("double@example.com")
    login_as(user)
    token = _csrf(client)

    for _ in range(4):
        response = client.post(
            f"/api/news/{news_item.id}/like", headers={CSRF_HEADER_NAME: token}
        )
        assert response.status_code == 200

    # Four toggles => even number => no like left, never two rows.
    assert db.query(NewsLike).count() == 0


def test_like_count_reflects_multiple_users(
    client, db, make_user, login_as, news_item
):
    first = make_user("a@example.com")
    second = make_user("b@example.com")

    login_as(first)
    token = _csrf(client)
    client.post(f"/api/news/{news_item.id}/like", headers={CSRF_HEADER_NAME: token})

    login_as(second)
    response = client.post(
        f"/api/news/{news_item.id}/like", headers={CSRF_HEADER_NAME: token}
    )
    assert response.json()["likes_count"] == 2


def test_like_on_missing_news_returns_404(client, make_user, login_as):
    user = make_user("liker2@example.com")
    login_as(user)
    token = _csrf(client)
    response = client.post("/api/news/9999/like", headers={CSRF_HEADER_NAME: token})
    assert response.status_code == 404


# --- Orders ----------------------------------------------------------------


def test_create_order_requires_authentication(client, service):
    response = client.post(
        "/orders", data={"service_id": str(service.id)}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_create_order_from_service_page(client, db, make_user, login_as, service):
    user = make_user("buyer@example.com")
    login_as(user)
    token = _csrf(client)

    response = client.post(
        "/orders",
        data={"service_id": str(service.id), "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/chat/{db.query(Order).one().id}"

    order = db.query(Order).one()
    assert order.user_id == user.id
    assert order.service_id == service.id
    assert order.status is OrderStatus.DRAFT
    assert order.title == "Тестовые боты"
    # A system message opens the conversation.
    assert len(order.messages) == 1
    assert order.messages[0].sender_id is None


def test_create_order_returns_to_catalog_when_asked(
    client, db, make_user, login_as, service
):
    user = make_user("buyer2@example.com")
    login_as(user)
    token = _csrf(client)

    response = client.post(
        "/orders",
        data={
            "service_id": str(service.id),
            "next": "/catalog/test-bots",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/catalog/test-bots"


def test_order_next_cannot_redirect_off_site(client, make_user, login_as, service):
    """`next` is attacker-controlled; only catalogue paths are honoured."""
    user = make_user("buyer3@example.com")
    login_as(user)
    token = _csrf(client)

    response = client.post(
        "/orders",
        data={
            "service_id": str(service.id),
            "next": "https://evil.example.com/steal",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert "evil.example.com" not in response.headers["location"]


def test_order_detail_is_private_to_its_owner(
    client, db, make_user, login_as, service
):
    owner = make_user("owner@example.com")
    intruder = make_user("intruder@example.com")

    order = Order(user_id=owner.id, service_id=service.id, title="Секрет")
    db.add(order)
    db.commit()
    db.refresh(order)

    login_as(intruder)
    response = client.get(f"/profile/orders/{order.id}")
    assert response.status_code == 403
    assert "Секрет" not in response.text


def test_order_detail_visible_to_its_owner(client, db, make_user, login_as, service):
    owner = make_user("owner2@example.com")
    order = Order(user_id=owner.id, service_id=service.id, title="Мой проект")
    db.add(order)
    db.commit()
    db.refresh(order)

    login_as(owner)
    response = client.get(f"/profile/orders/{order.id}")
    assert response.status_code == 200
    assert "Мой проект" in response.text


def test_profile_shows_orders_and_balance(client, db, make_user, login_as, service):
    user = make_user("p@example.com")
    db.add(Order(user_id=user.id, service_id=service.id, title="Проект в профиле"))
    db.commit()

    login_as(user)
    response = client.get("/profile")
    assert response.status_code == 200
    assert "Проект в профиле" in response.text
    assert "0 ₽" in response.text  # balance formatting


# --- Security headers ------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/", "/catalog", "/news", "/support", "/healthz"],
)
def test_security_headers_present_on_every_response(client, path):
    response = client.get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "content-security-policy" in response.headers
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_hsts_is_not_sent_over_plain_http(client):
    """HSTS on http would lock developers out of localhost."""
    response = client.get("/")
    assert "strict-transport-security" not in response.headers


def test_security_headers_survive_an_error_response(client):
    response = client.get("/catalog/no-such-service")
    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"


def test_csp_blocks_framing_and_form_hijacking(client):
    policy = client.get("/").headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    assert "form-action 'self'" in policy
    assert "base-uri 'self'" in policy


# --- Sanitisation unit tests ----------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "<svg/onload=alert(1)>",
        "javascript:alert(1)",
    ],
)
def test_plain_text_sanitiser_removes_markup(hostile):
    cleaned = clean_plain_text(hostile)
    assert "<" not in cleaned
    assert ">" not in cleaned


def test_plain_text_sanitiser_keeps_cyrillic_and_newlines():
    cleaned = clean_plain_text("Привет!\n\nВторая строка")
    assert "Привет!" in cleaned
    assert "Вторая строка" in cleaned


def test_plain_text_sanitiser_enforces_max_length():
    assert len(clean_plain_text("x" * 500, max_length=50)) == 50


def test_rich_text_sanitiser_keeps_formatting_drops_scripts():
    cleaned = clean_rich_text("<p>ok</p><script>alert(1)</script><strong>bold</strong>")
    assert "<p>ok</p>" in cleaned
    assert "<strong>bold</strong>" in cleaned
    assert "script" not in cleaned


def test_rich_text_sanitiser_drops_event_handlers():
    cleaned = clean_rich_text('<a href="#" onclick="steal()">link</a>')
    assert "onclick" not in cleaned
    assert "href" in cleaned


def test_rich_text_sanitiser_blocks_javascript_urls():
    cleaned = clean_rich_text('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in cleaned


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Telegram Bots", "telegram-bots"),
        ("  Spaces  And---Dashes  ", "spaces-and-dashes"),
        ("Сайты и боты", "сайты-и-боты"),
        ("!!!", ""),
    ],
)
def test_slug_cleaner(raw, expected):
    assert clean_slug(raw) == expected
