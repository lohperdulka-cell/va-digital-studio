"""Tests for the administrator dashboard: access control and CRUD."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import News, Order, Service, SupportTicket
from app.models.enums import MessageKind, OrderStatus, ServiceCategory, TicketStatus
from app.security.csrf import CSRF_COOKIE_NAME
from app.services import chat as chat_service

# --- Fixtures --------------------------------------------------------------


@pytest.fixture
def service(db) -> Service:
    item = Service(
        slug="dash-bots",
        title="Боты для дашборда",
        short_description="Описание",
        description="<p>Подробно</p>",
        category=ServiceCategory.BOTS,
        tags=["aiogram"],
        price_from=Decimal("30000.00"),
        duration_days=10,
        icon="🤖",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def order(db, make_user, service) -> Order:
    client_user = make_user("client@example.com", name="Клиент")
    item = Order(
        user_id=client_user.id,
        service_id=service.id,
        title="Нужен бот",
        description="Телеграм-бот для заявок",
        status=OrderStatus.DISCUSSING,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def ticket(db, make_user) -> SupportTicket:
    author = make_user("ticket@example.com", name="Автор")
    item = SupportTicket(
        user_id=author.id,
        email=author.email,
        name=author.name,
        subject="Не работает форма",
        message="При отправке формы появляется ошибка.",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture
def admin(make_user):
    return make_user("boss@example.com", is_admin=True, name="Админ")


@pytest.fixture
def news_item(db) -> News:
    item = News(
        slug="dash-news",
        title="Новость для дашборда",
        preview="Краткое описание",
        body="<p>Текст</p>",
        cover_emoji="📰",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _csrf(client) -> str:
    """Prime the CSRF cookie and return its value."""
    client.get("/")
    return client.cookies.get(CSRF_COOKIE_NAME)


# --- Access control --------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/dashboard/orders",
        "/dashboard/chats",
        "/dashboard/support",
        "/dashboard/services",
        "/dashboard/news",
    ],
)
def test_anonymous_is_redirected_to_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].startswith("/auth/login")


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/orders"])
def test_non_admin_is_forbidden(client, make_user, login_as, path):
    login_as(make_user("plain@example.com"))
    response = client.get(path)
    assert response.status_code == 403


# --- Rendering -------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/dashboard",
        "/dashboard/orders",
        "/dashboard/chats",
        "/dashboard/support",
        "/dashboard/services",
        "/dashboard/services/new",
        "/dashboard/news",
        "/dashboard/news/new",
    ],
)
def test_dashboard_pages_render(client, admin, login_as, service, order, ticket, path):
    login_as(admin)
    response = client.get(path)
    assert response.status_code == 200
    assert "dash__nav" in response.text


def test_overview_shows_counters(client, admin, login_as, order, ticket):
    login_as(admin)
    body = client.get("/dashboard").text
    assert "Заказов всего" in body
    assert "Открытых обращений" in body


def test_order_detail_renders_chat(client, admin, login_as, order):
    login_as(admin)
    response = client.get(f"/dashboard/orders/{order.id}")
    assert response.status_code == 200
    assert f'data-ws-path="/ws/chat/{order.id}"' in response.text
    assert "chat__log" in response.text


def test_order_detail_404_for_unknown(client, admin, login_as):
    login_as(admin)
    assert client.get("/dashboard/orders/999999").status_code == 404


def test_support_detail_renders_thread(client, admin, login_as, ticket):
    login_as(admin)
    response = client.get(f"/dashboard/support/{ticket.id}")
    assert response.status_code == 200
    assert "Не работает форма" in response.text


def test_orders_filter_by_status(client, admin, login_as, order):
    login_as(admin)
    matching = client.get("/dashboard/orders?status=discussing")
    assert matching.status_code == 200
    assert "Нужен бот" in matching.text

    other = client.get("/dashboard/orders?status=done")
    assert "Нужен бот" not in other.text


def test_orders_search_by_query(client, admin, login_as, order):
    login_as(admin)
    assert "Нужен бот" in client.get("/dashboard/orders?q=бот").text
    assert "Нужен бот" not in client.get("/dashboard/orders?q=зелёный").text


# --- Order mutations -------------------------------------------------------


def test_change_status(client, db, admin, login_as, order):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        f"/dashboard/orders/{order.id}/status",
        data={"status": "in_progress", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(order)
    assert order.status is OrderStatus.IN_PROGRESS


def test_change_status_rejects_unknown_value(client, db, admin, login_as, order):
    login_as(admin)
    token = _csrf(client)
    client.post(
        f"/dashboard/orders/{order.id}/status",
        data={"status": "teleported", "csrf_token": token},
        follow_redirects=False,
    )
    db.refresh(order)
    assert order.status is OrderStatus.DISCUSSING


def test_set_price(client, db, admin, login_as, order):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        f"/dashboard/orders/{order.id}/price",
        data={"price": "45 000", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(order)
    assert order.price_final == Decimal("45000.00")


def test_set_price_rejects_garbage(client, db, admin, login_as, order):
    login_as(admin)
    token = _csrf(client)
    client.post(
        f"/dashboard/orders/{order.id}/price",
        data={"price": "не число", "csrf_token": token},
        follow_redirects=False,
    )
    db.refresh(order)
    assert order.price_final is None


def test_price_can_be_cleared(client, db, admin, login_as, order):
    order.price_final = Decimal("1000.00")
    db.commit()

    login_as(admin)
    token = _csrf(client)
    client.post(
        f"/dashboard/orders/{order.id}/price",
        data={"price": "", "csrf_token": token},
        follow_redirects=False,
    )
    db.refresh(order)
    assert order.price_final is None


# --- Support mutations -----------------------------------------------------


def test_support_reply_closes_ticket(client, db, admin, login_as, ticket):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        f"/dashboard/support/{ticket.id}/reply",
        data={"body": "Здравствуйте! Мы починили форму.", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(ticket)
    assert ticket.status is TicketStatus.CLOSED
    assert ticket.replied_at is not None


def test_support_reply_too_short_is_rejected(client, db, admin, login_as, ticket):
    login_as(admin)
    token = _csrf(client)
    client.post(
        f"/dashboard/support/{ticket.id}/reply",
        data={"body": "ок", "csrf_token": token},
        follow_redirects=False,
    )
    db.refresh(ticket)
    assert ticket.status is TicketStatus.OPEN


def test_support_reopen(client, db, admin, login_as, ticket):
    ticket.status = TicketStatus.CLOSED
    db.commit()

    login_as(admin)
    token = _csrf(client)
    client.post(
        f"/dashboard/support/{ticket.id}/reopen",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    db.refresh(ticket)
    assert ticket.status is TicketStatus.OPEN


# --- Services CRUD ---------------------------------------------------------


def _service_form(**overrides) -> dict:
    payload = {
        "slug": "",
        "title": "Автоматизация процессов",
        "short_description": "Интеграции и сценарии",
        "description": "<p>Описание услуги</p>",
        "category": "automation",
        "tags": "n8n, интеграции, n8n",
        "price_from": "25 000",
        "duration_days": "21",
        "icon": "⚙️",
        "is_active": "1",
        "sort_order": "3",
    }
    payload.update(overrides)
    return payload


def test_create_service(client, db, admin, login_as):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        "/dashboard/services/save",
        data={**_service_form(), "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    created = db.query(Service).filter_by(title="Автоматизация процессов").one()
    assert created.slug == "автоматизация-процессов"
    assert created.price_from == Decimal("25000.00")
    assert created.tags == ["n8n", "интеграции"]
    assert created.duration_days == 21


def test_create_service_derives_slug_when_blank(client, db, admin, login_as, service):
    """A blank slug must not collide with the existing service."""
    login_as(admin)
    token = _csrf(client)
    client.post(
        "/dashboard/services/save",
        data={**_service_form(slug="", title="Боты для дашборда"), "csrf_token": token},
        follow_redirects=False,
    )
    titles = [s.title for s in db.query(Service).all()]
    assert titles.count("Боты для дашборда") == 2
    slugs = {s.slug for s in db.query(Service).all()}
    assert len(slugs) == 2  # the second one got a suffixed slug


def test_create_service_rejects_short_title(client, db, admin, login_as):
    login_as(admin)
    token = _csrf(client)
    client.post(
        "/dashboard/services/save",
        data={**_service_form(title="X"), "csrf_token": token},
        follow_redirects=False,
    )
    assert db.query(Service).filter_by(title="X").count() == 0


def test_update_service(client, db, admin, login_as, service):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        "/dashboard/services/save",
        data={
            **_service_form(
                slug=service.slug,
                title="Боты (обновлено)",
                is_active="",
            ),
            "service_id": str(service.id),
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.refresh(service)
    assert service.title == "Боты (обновлено)"
    assert service.is_active is False


def test_delete_service(client, db, admin, login_as, service):
    service_id = service.id
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        f"/dashboard/services/{service_id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(Service).filter_by(id=service_id).first() is None


# --- News CRUD -------------------------------------------------------------


def _news_form(**overrides) -> dict:
    payload = {
        "slug": "",
        "title": "Запустили новый сервис",
        "preview": "Коротко о запуске",
        "body": "<p>Полный текст новости</p>",
        "cover_emoji": "🚀",
        "is_published": "1",
    }
    payload.update(overrides)
    return payload


def test_create_news(client, db, admin, login_as):
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        "/dashboard/news/save",
        data={**_news_form(), "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(News).filter_by(title="Запустили новый сервис").count() == 1


def test_create_news_as_draft_is_hidden_publicly(client, db, admin, login_as):
    login_as(admin)
    token = _csrf(client)
    client.post(
        "/dashboard/news/save",
        data={**_news_form(title="Черновик", is_published=""), "csrf_token": token},
        follow_redirects=False,
    )
    item = db.query(News).filter_by(title="Черновик").one()
    assert item.is_published is False


def test_update_news(client, db, admin, login_as, news_item):
    login_as(admin)
    token = _csrf(client)
    client.post(
        "/dashboard/news/save",
        data={
            **_news_form(slug=news_item.slug, title="Обновлённый заголовок"),
            "news_id": str(news_item.id),
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    db.refresh(news_item)
    assert news_item.title == "Обновлённый заголовок"


def test_delete_news(client, db, admin, login_as, news_item):
    news_id = news_item.id
    login_as(admin)
    token = _csrf(client)
    response = client.post(
        f"/dashboard/news/{news_id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.query(News).filter_by(id=news_id).first() is None


# --- CSRF on dashboard POSTs ----------------------------------------------


@pytest.mark.parametrize(
    "path,data",
    [
        ("/dashboard/orders/{order_id}/status", {"status": "done"}),
        ("/dashboard/orders/{order_id}/price", {"price": "100"}),
    ],
)
def test_order_posts_require_csrf(client, admin, login_as, order, path, data):
    login_as(admin)
    response = client.post(path.format(order_id=order.id), data=data)
    assert response.status_code == 403


def test_support_reply_requires_csrf(client, admin, login_as, ticket):
    login_as(admin)
    response = client.post(
        f"/dashboard/support/{ticket.id}/reply", data={"body": "Ответ без токена"}
    )
    assert response.status_code == 403


# --- Chats and unread counters --------------------------------------------


def test_chats_page_lists_conversations(client, db, admin, login_as, order):
    """An order with a message shows up; an empty room does not."""
    chat_service.save_message(
        db, order_id=order.id, sender_id=order.user_id, text="Здравствуйте!",
        kind=MessageKind.CLIENT,
    )
    login_as(admin)
    body = client.get("/dashboard/chats").text
    assert f"#{order.id}" in body


def test_chats_page_previews_the_newest_message(client, db, admin, login_as, order):
    for text in ("Первое сообщение", "Самое новое сообщение"):
        chat_service.save_message(
            db, order_id=order.id, sender_id=order.user_id, text=text,
            kind=MessageKind.CLIENT,
        )
    login_as(admin)
    body = client.get("/dashboard/chats").text
    assert "Самое новое сообщение" in body
    assert "Первое сообщение" not in body


def test_unread_badge_counts_client_messages(client, db, admin, login_as, order):
    for text in ("Первое", "Второе"):
        chat_service.save_message(
            db, order_id=order.id, sender_id=order.user_id, text=text,
            kind=MessageKind.CLIENT,
        )
    login_as(admin)
    body = client.get("/dashboard/chats").text
    assert 'class="dash__count"' in body
    assert ">2<" in body


def test_admin_reply_does_not_count_as_unread_for_admin(client, db, admin, login_as, order):
    chat_service.save_message(
        db, order_id=order.id, sender_id=admin.id, text="Ответ менеджера",
        kind=MessageKind.STAFF,
    )
    login_as(admin)
    body = client.get("/dashboard/chats").text
    assert 'class="dash__count"' not in body
