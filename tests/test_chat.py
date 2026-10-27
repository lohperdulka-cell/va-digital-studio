"""Order chat: HTTP page access control and the live WebSocket protocol."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models import ChatMessage, Order, Service
from app.models.enums import MessageKind, OrderStatus, ServiceCategory
from app.security.sessions import SESSION_COOKIE_NAME
from app.security.tokens import create_session_token
from app.services import chat as chat_service


def _login(client: TestClient, user) -> None:
    """Attach a valid session cookie to an arbitrary client."""
    token, _expires = create_session_token(
        user_id=user.id, email=user.email, is_admin=user.is_admin
    )
    client.cookies.set(SESSION_COOKIE_NAME, token)

# --- Fixtures --------------------------------------------------------------


@pytest.fixture
def service(db):
    service = Service(
        slug="website-development",
        title="Разработка сайтов",
        short_description="Сайты под ключ",
        description="Полный цикл разработки",
        category=ServiceCategory.SITES,
        tags=["landing", "cms"],
        price_from=30000,
        duration_days=14,
        is_active=True,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@pytest.fixture
def order(db, make_user, service):
    owner = make_user("client@example.com")
    order = Order(
        user_id=owner.id,
        service_id=service.id,
        title="Корпоративный сайт",
        description="Нужен сайт на 10 страниц",
        status=OrderStatus.DISCUSSING,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


# --- HTTP access control ---------------------------------------------------


def test_anonymous_visitor_cannot_open_chat(client, order):
    response = client.get(f"/chat/{order.id}", follow_redirects=False)
    # Protected routes bounce anonymous visitors to Google sign-in.
    assert response.status_code == 303
    assert "/auth/login" in response.headers["location"]


def test_owner_can_open_chat(client, login_as, order):
    login_as(order.user)
    response = client.get(f"/chat/{order.id}")
    assert response.status_code == 200
    # The header names the studio, not an individual member of staff.
    assert "Поддержка VA Digital" in response.text
    assert f'data-ws-path="/ws/chat/{order.id}"' in response.text
    # The info strip carries the order number, its status and the price.
    assert f'#{order.id}' in response.text
    assert "Цена" in response.text


def test_another_user_is_forbidden(client, login_as, make_user, order):
    stranger = make_user("stranger@example.com")
    login_as(stranger)
    response = client.get(f"/chat/{order.id}")
    assert response.status_code == 403


def test_admin_can_open_any_chat(client, login_as, make_user, order):
    login_as(make_user("boss@example.com", is_admin=True))
    response = client.get(f"/chat/{order.id}")
    assert response.status_code == 200
    # Staff see the client's own name in the header.
    assert order.user.display_name in response.text


def test_missing_order_returns_404(client, login_as, order):
    login_as(order.user)
    assert client.get("/chat/999999").status_code == 404


# --- WebSocket handshake ---------------------------------------------------


def test_websocket_rejects_anonymous_connection(client, order):
    """The handshake is refused with an application close code."""
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(f"/ws/chat/{order.id}") as socket,
    ):
        socket.receive_json()
    assert excinfo.value.code == 4401


def test_websocket_reports_a_missing_order_to_an_authenticated_user(
    client, login_as, order
):
    """A signed-in visitor gets 4404 rather than a silent failure."""
    login_as(order.user)
    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/ws/chat/999999") as socket,
    ):
        socket.receive_json()
    assert excinfo.value.code == 4404


def test_websocket_sends_history_to_the_owner(client, login_as, db, order):
    db.add(
        ChatMessage(
            order_id=order.id,
            sender_id=order.user_id,
            kind=MessageKind.CLIENT,
            text="Здравствуйте, есть вопрос",
        )
    )
    db.commit()

    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        payload = socket.receive_json()
        assert payload["type"] == "history"
        assert payload["order_id"] == order.id
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["text"] == "Здравствуйте, есть вопрос"
        assert payload["messages"][0]["is_mine"] is True


def test_message_is_persisted_and_echoed(client, login_as, db, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()  # history
        socket.send_json({"type": "message", "text": "Когда старт?"})
        payload = socket.receive_json()
        assert payload["type"] == "message"
        assert payload["message"]["text"] == "Когда старт?"
        assert payload["message"]["is_mine"] is True

    db.expire_all()
    stored = db.query(ChatMessage).filter_by(order_id=order.id).all()
    assert [message.text for message in stored] == ["Когда старт?"]


def test_message_is_sanitised_before_storage(client, login_as, db, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json(
            {"type": "message", "text": "<script>alert(1)</script>привет"}
        )
        payload = socket.receive_json()
        assert "<script>" not in payload["message"]["text"]
        assert "привет" in payload["message"]["text"]

    db.expire_all()
    stored = db.query(ChatMessage).filter_by(order_id=order.id).one()
    assert "<script>" not in stored.text


def test_empty_message_is_rejected(client, login_as, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json({"type": "message", "text": "   "})
        payload = socket.receive_json()
        assert payload["type"] == "error"


def test_oversized_message_is_rejected(client, login_as, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        # Above the 16 KB frame cap, so it is refused before parsing.
        socket.send_json({"type": "message", "text": "x" * 20000})
        payload = socket.receive_json()
        assert payload["type"] == "error"


def test_flooding_the_chat_is_throttled(client, login_as, order):
    """A single user cannot exceed the per-minute message budget."""
    from app.routes import chat as chat_routes

    login_as(order.user)
    original = chat_routes._chat_limiter.limit
    chat_routes._chat_limiter.limit = 3
    try:
        with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
            socket.receive_json()
            for _ in range(3):
                socket.send_json({"type": "message", "text": "привет"})
                assert socket.receive_json()["type"] == "message"

            socket.send_json({"type": "message", "text": "ещё одно"})
            payload = socket.receive_json()
            assert payload["type"] == "error"
            assert "Слишком много" in payload["detail"]
    finally:
        chat_routes._chat_limiter.limit = original


def test_typing_frames_are_not_persisted(client, login_as, db, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json({"type": "typing", "is_typing": True})
        # A typing frame produces no message back to its own sender.
        socket.send_json({"type": "message", "text": "проверка"})
        payload = socket.receive_json()
        assert payload["type"] == "message"

    db.expire_all()
    assert db.query(ChatMessage).count() == 1


def test_unknown_frame_type_is_reported(client, login_as, order):
    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json({"type": "nonsense"})
        payload = socket.receive_json()
        assert payload["type"] == "error"


def test_two_participants_see_each_others_messages(make_user, order):
    """Client and admin in the same room; ``is_mine`` differs per viewer.

    Two independent clients are needed: a single ``TestClient`` shares one
    cookie jar, so both sockets would authenticate as the same user.
    """
    admin = make_user("boss@example.com", is_admin=True)

    with (
        TestClient(app) as client_side,
        TestClient(app) as admin_side,
    ):
        _login(client_side, order.user)
        _login(admin_side, admin)

        with client_side.websocket_connect(f"/ws/chat/{order.id}") as client_socket:
            client_socket.receive_json()  # history

            with admin_side.websocket_connect(
                f"/ws/chat/{order.id}"
            ) as admin_socket:
                admin_socket.receive_json()  # admin history

                admin_socket.send_json({"type": "message", "text": "Здравствуйте!"})

                # Both sides receive the same message with different ownership.
                as_admin = admin_socket.receive_json()
                as_client = client_socket.receive_json()
                assert as_admin["message"]["is_mine"] is True
                assert as_client["message"]["is_mine"] is False
                assert as_client["message"]["text"] == "Здравствуйте!"


# --- Service-level rules ---------------------------------------------------


def test_mark_read_flips_only_the_other_side(db, order, make_user):
    admin = make_user("boss@example.com", is_admin=True)
    db.add_all(
        [
            ChatMessage(
                order_id=order.id,
                sender_id=order.user_id,
                kind=MessageKind.CLIENT,
                text="клиент",
            ),
            ChatMessage(
                order_id=order.id,
                sender_id=admin.id,
                kind=MessageKind.STAFF,
                text="менеджер",
            ),
        ]
    )
    db.commit()

    # The client reading marks staff messages, not their own.
    changed = chat_service.mark_read(db, order_id=order.id, is_admin=False)
    assert changed == 1

    db.expire_all()
    rows = {message.kind: message.is_read for message in db.query(ChatMessage).all()}
    assert rows[MessageKind.STAFF] is True
    assert rows[MessageKind.CLIENT] is False


def test_cancelled_order_chat_is_closed(client, login_as, db, order):
    order.status = OrderStatus.CANCELLED
    db.commit()

    login_as(order.user)
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json({"type": "message", "text": "ещё вопрос"})
        payload = socket.receive_json()
        assert payload["type"] == "error"
        assert "закрыт" in payload["detail"]


def test_finished_order_chat_is_read_only_for_the_client(
    client, login_as, db, order
):
    """A completed order shows a support button instead of the input."""
    order.status = OrderStatus.DONE
    db.commit()

    login_as(order.user)
    response = client.get(f"/chat/{order.id}")
    assert response.status_code == 200
    assert "Обратиться в поддержку" in response.text
    # The form itself is gone; the selector string survives only inside the
    # script that wires the client up.
    assert 'id="chat-input-' not in response.text
    assert "chat__closed" in response.text


def test_finished_order_chat_still_accepts_staff_messages(
    client, login_as, make_user, db, order
):
    """Staff keep writing after completion — that is how support continues."""
    order.status = OrderStatus.DONE
    db.commit()

    login_as(make_user("boss@example.com", is_admin=True))
    with client.websocket_connect(f"/ws/chat/{order.id}") as socket:
        socket.receive_json()
        socket.send_json({"type": "message", "text": "Мы на связи"})
        payload = socket.receive_json()
        assert payload["type"] == "message"
        assert payload["message"]["text"] == "Мы на связи"


def test_completed_order_shows_a_support_link_with_the_order_number(
    client, login_as, db, order
):
    order.status = OrderStatus.DONE
    db.commit()

    login_as(order.user)
    response = client.get(f"/chat/{order.id}")
    assert f"/support?order={order.id}" in response.text
