"""Email+password and Telegram sign-in.

Kept apart from :mod:`app.routes.auth` (which owns the Google OAuth dance and
logout) so each entry path stays small and readable.

Route map::

    GET  /auth/login          sign-in page (email+password is the primary form)
    POST /auth/login          password sign-in
    GET  /auth/register       registration form
    POST /auth/register       create an email+password account
    GET  /auth/telegram       Telegram sign-in page (deep link to the bot)
    POST /auth/telegram       send a code into the Telegram chat
    POST /auth/telegram/verify  redeem the Telegram code

Every POST is CSRF-guarded and rate limited (``/auth/`` is in the limiter's
guarded prefixes), and every field is validated before it reaches the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from app.config import settings
from app.errors import AppError
from app.logging_config import get_logger
from app.schemas.auth import (
    CodeVerifyForm,
    LoginForm,
    RegisterForm,
    TelegramStartForm,
)
from app.security.csrf import require_csrf
from app.security.deps import DbSession
from app.security.passwords import PasswordPolicyError
from app.security.sessions import issue_session
from app.security.tokens import safe_next_path
from app.services import accounts as account_service
from app.services import login_codes, telegram
from app.services.accounts import EmailTakenError, UsernameTakenError
from app.services.login_codes import CodeError
from app.templating import render

router = APIRouter(prefix="/auth", tags=["login"], dependencies=[Depends(require_csrf)])
logger = get_logger(__name__)


class LoginError(AppError):
    status_code = 400
    title = "Не удалось войти"


def _first_error(exc: ValidationError) -> str:
    """Turn a pydantic error into one short, user-facing sentence."""
    error = exc.errors()[0]
    message = str(error.get("msg", "")).replace("Value error, ", "")
    return message or "Проверьте введённые данные"


def _form_values(exc: ValidationError) -> dict[str, list[str]]:
    """Group messages by field so the template can place them inline."""
    grouped: dict[str, list[str]] = {}
    for error in exc.errors():
        field = str(error["loc"][0]) if error.get("loc") else "form"
        message = str(error.get("msg", "")).replace("Value error, ", "")
        grouped.setdefault(field, []).append(message)
    return grouped


def _render_login(
    request: Request,
    *,
    errors: list[str] | None = None,
    field_errors: dict[str, list[str]] | None = None,
    values: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return render(
        request,
        "login.html",
        {
            "errors": errors or [],
            "field_errors": field_errors or {},
            "values": values or {},
            "google_enabled": settings.oauth_configured,
            "telegram_enabled": settings.telegram_configured,
            "next_url": _next_from(request),
        },
        status_code=status_code,
    )


def _next_from(request: Request) -> str:
    return safe_next_path(request.query_params.get("next"))


# --- Password sign-in ------------------------------------------------------


@router.get("/login")
def login_page(request: Request) -> Response:
    """The sign-in page. Google is offered as an alternative when configured."""
    return _render_login(request)


@router.post("/login")
def login_submit(
    request: Request,
    db: DbSession,
    login: str = Form(default=""),
    password: str = Form(default=""),
    next: str = Form(default=""),
) -> Response:
    try:
        form = LoginForm(login=login, password=password, next=next)
    except ValidationError as exc:
        return _render_login(
            request,
            field_errors=_form_values(exc),
            values={"login": login},
            status_code=400,
        )

    user = account_service.authenticate_password(
        db, login=form.login, password=form.password
    )
    if user is None:
        logger.info("Rejected password login for %s", form.login)
        return _render_login(
            request,
            errors=["Неверный e-mail/логин или пароль"],
            values={"login": form.login},
            status_code=401,
        )

    target = safe_next_path(form.next or _next_from(request))
    response = RedirectResponse(target, status_code=303)
    issue_session(response, user)
    logger.info("Password login: user_id=%s", user.id)
    return response


# --- Registration ----------------------------------------------------------


@router.get("/register")
def register_page(request: Request) -> Response:
    return render(
        request,
        "register.html",
        {
            "errors": [],
            "field_errors": {},
            "values": {},
            "google_enabled": settings.oauth_configured,
            "next_url": _next_from(request),
        },
    )


@router.post("/register")
def register_submit(
    request: Request,
    db: DbSession,
    username: str = Form(default=""),
    email: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    name: str = Form(default=""),
) -> Response:
    try:
        form = RegisterForm(
            username=username,
            email=email,
            password=password,
            password_confirm=password_confirm,
            name=name,
        )
    except ValidationError as exc:
        return render(
            request,
            "register.html",
            {
                "errors": [],
                "field_errors": _form_values(exc),
                "values": {"email": email, "name": name, "username": username},
                "google_enabled": settings.oauth_configured,
                "next_url": _next_from(request),
            },
            status_code=400,
        )

    try:
        user = account_service.register_with_password(
            db,
            email=form.email,
            password=form.password,
            name=form.name,
            username=form.username,
        )
    except (
        EmailTakenError,
        UsernameTakenError,
        PasswordPolicyError,
    ) as exc:
        return render(
            request,
            "register.html",
            {
                "errors": [str(exc)],
                "field_errors": {},
                "values": {"email": email, "name": name, "username": username},
                "google_enabled": settings.oauth_configured,
                "next_url": _next_from(request),
            },
            status_code=400,
        )

    response = RedirectResponse(safe_next_path(_next_from(request)), status_code=303)
    issue_session(response, user)
    logger.info("Registration login: user_id=%s", user.id)
    return response


# --- Telegram --------------------------------------------------------------


@router.get("/telegram")
def telegram_page(request: Request) -> Response:
    """Explain the flow and, when an e-mail is supplied, offer the deep link."""
    email = (request.query_params.get("email") or "").strip().lower()
    start_url = ""
    if email and "@" in email and settings.telegram_configured:
        start_url = telegram.deep_link(
            start_payload=telegram.create_start_payload(email)
        )

    return render(
        request,
        "login_telegram.html",
        {
            "errors": [],
            "field_errors": {},
            "values": {"email": email},
            "telegram_enabled": settings.telegram_configured,
            "bot_username": telegram.bot_username(),
            "start_url": start_url,
            "stage": "verify" if start_url else "request",
            "next_url": _next_from(request),
        },
    )


@router.post("/telegram")
def telegram_send(
    request: Request,
    db: DbSession,
    email: str = Form(default=""),
    next: str = Form(default=""),
) -> Response:
    """Send a login code into the visitor's Telegram chat."""
    try:
        form = TelegramStartForm(email=email)
    except ValidationError as exc:
        return render(
            request,
            "login_telegram.html",
            {
                "errors": [],
                "field_errors": _form_values(exc),
                "values": {"email": email},
                "telegram_enabled": settings.telegram_configured,
                "bot_username": telegram.bot_username(),
                "start_url": "",
                "stage": "request",
                "next_url": _next_from(request),
            },
            status_code=400,
        )

    if not settings.telegram_configured:
        return render(
            request,
            "login_telegram.html",
            {
                "errors": ["Вход через Telegram пока не настроен."],
                "field_errors": {},
                "values": {"email": form.email},
                "telegram_enabled": False,
                "bot_username": "",
                "start_url": "",
                "stage": "request",
                "next_url": _next_from(request),
            },
            status_code=503,
        )

    # The bot is the only party that knows the chat id, so the code is created
    # now and delivered when the visitor presses Start.  The signed payload
    # carries the e-mail; the bot echoes it back to /auth/telegram/verify.
    payload = telegram.create_start_payload(form.email)
    start_url = telegram.deep_link(start_payload=payload)

    return render(
        request,
        "login_telegram.html",
        {
            "errors": [],
            "field_errors": {},
            "values": {"email": form.email},
            "telegram_enabled": True,
            "bot_username": telegram.bot_username(),
            "start_url": start_url,
            "stage": "verify",
            "next_url": safe_next_path(next or _next_from(request)),
        },
    )


@router.post("/telegram/verify")
def telegram_verify(
    request: Request,
    db: DbSession,
    email: str = Form(default=""),
    code: str = Form(default=""),
    next: str = Form(default=""),
) -> Response:
    try:
        form = CodeVerifyForm(email=email, code=code)
    except ValidationError as exc:
        return render(
            request,
            "login_telegram.html",
            {
                "errors": [],
                "field_errors": _form_values(exc),
                "values": {"email": email},
                "telegram_enabled": settings.telegram_configured,
                "bot_username": telegram.bot_username(),
                "start_url": "",
                "stage": "verify",
                "next_url": _next_from(request),
            },
            status_code=400,
        )

    try:
        record = login_codes.redeem_code(
            db, email=form.email, code=form.code, channel=login_codes.CHANNEL_TELEGRAM
        )
    except CodeError as exc:
        return render(
            request,
            "login_telegram.html",
            {
                "errors": [str(exc)],
                "field_errors": {},
                "values": {"email": form.email},
                "telegram_enabled": settings.telegram_configured,
                "bot_username": telegram.bot_username(),
                "start_url": "",
                "stage": "verify",
                "next_url": _next_from(request),
            },
            status_code=400,
        )

    user, _created = account_service.upsert_by_email_code(
        db,
        email=form.email,
        telegram_id=record.telegram_id,
        telegram_username=record.telegram_username,
    )
    response = RedirectResponse(
        safe_next_path(next or _next_from(request)), status_code=303
    )
    issue_session(response, user)
    logger.info("Telegram login: user_id=%s", user.id)
    return response
