"""Application-level exceptions and their HTTP handlers."""

from __future__ import annotations

from fastapi import Request, status


class AppError(Exception):
    """Base class for errors we deliberately surface to the user."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Ошибка"
    detail: str = "Что-то пошло не так"

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class NotAuthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Требуется вход"
    detail = "Войдите через Google, чтобы продолжить"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    title = "Доступ запрещён"
    detail = "У вас нет прав для просмотра этой страницы"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Страница не найдена"
    detail = "Такой страницы не существует"


def wants_json(request: Request) -> bool:
    """True for API/WebSocket-adjacent calls that expect a JSON error body."""
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept
