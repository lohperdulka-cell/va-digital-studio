"""Order chat over WebSocket, plus the HTML page that hosts it.

Authentication happens during the handshake: the session JWT is read from the
``va_session`` cookie and verified before the socket is accepted, so an
anonymous client is closed with code 4401 rather than being allowed to sit on
an open connection.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.database import SessionLocal
from app.errors import ForbiddenError, NotFoundError
from app.logging_config import get_logger
from app.models import Order
from app.models.enums import MessageKind, OrderStatus
from app.schemas import ChatMessageIn
from app.security.deps import CurrentUser, DbSession
from app.security.ratelimit import RateLimiter
from app.security.sessions import SESSION_COOKIE_NAME, user_from_request
from app.services import chat as chat_service
from app.services import orders as order_service
from app.templating import render

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])

# Custom close codes (4000-4999 is the application-defined range).
WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404
WS_TOO_LARGE = 4409

MAX_FRAME_BYTES = 16 * 1024

# The HTTP middleware cannot see WebSocket frames, so the socket carries its own
# budget.  Keyed by user id rather than IP: one account cannot flood a chat.
CHAT_MESSAGES_PER_MINUTE = 30
_chat_limiter = RateLimiter(limit=CHAT_MESSAGES_PER_MINUTE, window_seconds=60)


def _order_for_viewer(
    db, order_id: int, *, user_id: int, is_admin: bool
) -> Order | None:
    order = db.get(Order, order_id)
    if order is None:
        return None
    if not chat_service.can_access(order, user_id=user_id, is_admin=is_admin):
        return None
    return order


# --- HTML page -------------------------------------------------------------


@router.get("/chat/{order_id}")
def chat_page(
    request: Request,
    order_id: int,
    user: CurrentUser,
    db: DbSession,
):
    order = order_service.get_order(db, order_id)
    if order is None:
        raise NotFoundError(detail="Заказ не найден")
    if not chat_service.can_access(order, user_id=user.id, is_admin=user.is_admin):
        logger.warning(
            "Chat access denied: order_id=%s owner=%s requester=%s",
            order_id,
            order.user_id,
            user.id,
        )
        raise ForbiddenError(detail="Этот чат принадлежит другому пользователю")

    # An admin who owns the order sees it as a client, not as staff.
    as_admin = user.is_admin and order.user_id != user.id

    return render(
        request,
        "chat.html",
        {
            "order": order,
            "as_admin": as_admin,
            "ws_path": f"/ws/chat/{order.id}",
        },
    )


# --- WebSocket -------------------------------------------------------------


@router.websocket("/ws/chat/{order_id}")
async def chat_socket(websocket: WebSocket, order_id: int) -> None:
    """Live chat for one order.

    The session cookie is verified before any message is exchanged.  We accept
    first so the client receives an application close code (4401/4403/4404)
    instead of an opaque HTTP 403 — that lets the browser page distinguish
    "sign in again" from "transient network drop" and stop reconnecting.
    """
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    # A short-lived session is used only to resolve the user, then closed.
    db = SessionLocal()
    try:
        user = user_from_request(websocket, db)
        if user is None:
            await websocket.accept()
            await websocket.close(code=WS_UNAUTHORIZED)
            return
        user_id, is_admin, display_name = user.id, user.is_admin, user.display_name
        order = _order_for_viewer(
            db, order_id, user_id=user_id, is_admin=is_admin
        )
        if order is None:
            await websocket.accept()
            await websocket.close(code=WS_NOT_FOUND)
            return
    finally:
        db.close()

    await websocket.accept()
    connection = chat_service.Connection(
        websocket=websocket,
        order_id=order_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    chat_service.hub.add(connection)

    db = SessionLocal()
    try:
        history = chat_service.load_history(db, order_id)
        await connection.send(
            {
                "type": "history",
                "order_id": order_id,
                "messages": [
                    {**message.to_payload(), "is_mine": message.sender_id == user_id}
                    for message in history
                ],
            }
        )
        chat_service.mark_read(db, order_id=order_id, is_admin=is_admin)
    except Exception:
        logger.exception("Failed to send chat history: order_id=%s", order_id)
    finally:
        db.close()

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_FRAME_BYTES:
                await connection.send(
                    {"type": "error", "detail": "Сообщение слишком длинное"}
                )
                continue
            allowed, _remaining, retry_after = _chat_limiter.check(str(user_id))
            if not allowed:
                logger.warning(
                    "Chat rate limit hit: user_id=%s order_id=%s", user_id, order_id
                )
                await connection.send(
                    {
                        "type": "error",
                        "detail": (
                            "Слишком много сообщений. Подождите "
                            f"{int(retry_after) + 1} с."
                        ),
                    }
                )
                continue
            await _handle_frame(
                connection,
                raw,
                order_id=order_id,
                user_id=user_id,
                is_admin=is_admin,
                display_name=display_name,
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Chat socket error: order_id=%s user_id=%s", order_id, user_id)
    finally:
        chat_service.hub.remove(connection)


async def _handle_frame(
    connection: chat_service.Connection,
    raw: str,
    *,
    order_id: int,
    user_id: int,
    is_admin: bool,
    display_name: str,
) -> None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        await connection.send({"type": "error", "detail": "Некорректный формат"})
        return

    if not isinstance(payload, dict):
        await connection.send({"type": "error", "detail": "Некорректный формат"})
        return

    frame_type = payload.get("type")

    if frame_type == "typing":
        await chat_service.hub.broadcast_typing(
            order_id,
            sender=connection,
            is_typing=bool(payload.get("is_typing")),
            sender_name=display_name,
        )
        return

    if frame_type != "message":
        await connection.send({"type": "error", "detail": "Неизвестный тип"})
        return

    try:
        incoming = ChatMessageIn(text=str(payload.get("text", "")))
    except ValidationError:
        await connection.send(
            {"type": "error", "detail": "Сообщение не может быть пустым"}
        )
        return

    db = SessionLocal()
    try:
        # Re-check on every message: the order may have been cancelled or the
        # visitor signed out in another tab.
        order = _order_for_viewer(db, order_id, user_id=user_id, is_admin=is_admin)
        if order is None:
            await connection.send({"type": "error", "detail": "Нет доступа к чату"})
            return
        if order.status is OrderStatus.CANCELLED:
            await connection.send(
                {"type": "error", "detail": "Заказ отменён — чат закрыт"}
            )
            return

        payload = chat_service.save_message(
            db,
            order_id=order_id,
            sender_id=user_id,
            text=incoming.text,
            kind=MessageKind.STAFF if is_admin else MessageKind.CLIENT,
        )
    except Exception:
        logger.exception("Failed to persist chat message: order_id=%s", order_id)
        await connection.send({"type": "error", "detail": "Не удалось отправить"})
        return
    finally:
        db.close()

    await chat_service.hub.broadcast_message(order_id, payload)
