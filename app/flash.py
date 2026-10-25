"""One-shot messages carried across a redirect.

Stored in the Starlette session cookie, which is signed and httponly, so a
visitor cannot forge a message.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Request

FlashLevel = Literal["info", "success", "warning", "error"]

_SESSION_KEY = "_flashes"
_MAX_PENDING = 8


def flash(request: Request, message: str, level: FlashLevel = "info") -> None:
    """Queue a message for the next rendered page."""
    try:
        session = request.session
    except AssertionError:  # pragma: no cover - SessionMiddleware is always on
        return
    pending: list[dict[str, Any]] = session.get(_SESSION_KEY) or []
    pending.append({"message": message, "level": level})
    # Keep the cookie small; old messages are dropped, not accumulated.
    session[_SESSION_KEY] = pending[-_MAX_PENDING:]


def get_flashed_messages(request: Request) -> list[dict[str, Any]]:
    """Return and clear the queued messages."""
    try:
        session = request.session
    except AssertionError:  # pragma: no cover
        return []
    return session.pop(_SESSION_KEY, []) or []
