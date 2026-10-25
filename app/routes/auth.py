"""Google OAuth 2.0 login, callback and logout.

Flow
----
1. ``GET /auth/login`` mints a signed ``state`` token (CSRF protection for the
   OAuth dance), stores it in a short-lived httponly cookie, and redirects to
   Google.  authlib also stashes its PKCE verifier and nonce in the encrypted
   Starlette session cookie.
2. ``GET /auth/callback`` verifies that the ``state`` Google returned matches
   the cookie (double-submit), lets authlib validate the ID token signature and
   nonce, then issues our own JWT session cookie.

Defence in depth: the state is checked twice — once against our signed token
and once inside authlib's own session store.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.logging_config import get_logger
from app.security.csrf import require_csrf
from app.security.oauth import get_oauth
from app.security.sessions import (
    STATE_COOKIE_NAME,
    clear_handshake_cookies,
    clear_session_cookie,
    issue_session,
    set_handshake_cookie,
)
from app.security.tokens import (
    STATE_TTL_SECONDS,
    constant_time_equals,
    create_state_token,
    decode_state_token,
    safe_next_path,
)
from app.services.accounts import OAuthProfileError, profile_from_id_token, upsert_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.get("/login")
async def login(request: Request, next: str | None = None) -> Response:
    """Kick off the Google consent screen."""
    oauth = get_oauth()
    if oauth is None:
        logger.warning("Login attempted but Google OAuth is not configured")
        return _config_error_page()

    target = safe_next_path(next)
    state, _nonce = create_state_token(target)

    try:
        client = oauth.create_client("google")
        redirect = await client.authorize_redirect(
            request, settings.google_redirect_uri, state=state
        )
    except Exception:
        logger.exception("Failed to build the Google authorize URL")
        return _config_error_page(
            "Не удалось связаться с Google. Проверьте настройки OAuth."
        )

    response = RedirectResponse(redirect.headers["location"], status_code=302)
    set_handshake_cookie(response, STATE_COOKIE_NAME, state, STATE_TTL_SECONDS)
    logger.info("OAuth login started, next=%s", target)
    return response


@router.get("/callback")
async def callback(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Handle Google's redirect back to us."""
    # Validate the request itself before touching configuration, so the CSRF
    # check on `state` always runs and the response never varies with setup.
    error = request.query_params.get("error")
    if error:
        logger.warning("Google returned an OAuth error: %s", error)
        return _error_page("Вход через Google был отменён.")

    state = request.query_params.get("state") or ""
    cookie_state = request.cookies.get(STATE_COOKIE_NAME) or ""
    claims = decode_state_token(state)

    if (
        not state
        or not cookie_state
        or claims is None
        or not constant_time_equals(state, cookie_state)
    ):
        logger.warning("OAuth state mismatch — possible CSRF attempt")
        return _error_page("Проверка безопасности не пройдена. Попробуйте войти снова.")

    oauth = get_oauth()
    if oauth is None:
        return _config_error_page()

    client = oauth.create_client("google")
    try:
        token = await client.authorize_access_token(request)
    except Exception:
        logger.exception("Google token exchange failed")
        return _error_page("Не удалось завершить вход. Попробуйте ещё раз.")

    # authlib parses and validates the ID token (signature, issuer, audience,
    # expiry, nonce) and exposes the payload as `userinfo`.
    id_claims = token.get("userinfo")
    if not id_claims:
        logger.warning("Google token response contained no verified userinfo")
        return _error_page("Google вернул некорректные данные.")

    try:
        profile = profile_from_id_token(dict(id_claims))
    except OAuthProfileError as exc:
        logger.warning("Rejected OAuth profile: %s", exc)
        return _error_page(str(exc))

    user, _created = upsert_user(db, profile)

    response = RedirectResponse(safe_next_path(claims.get("nxt")), status_code=303)
    issue_session(response, user)
    clear_handshake_cookies(response)
    return response


async def _logout(request: Request) -> Response:
    user = getattr(request.state, "user", None)
    if user is not None:
        logger.info("Logout: user_id=%s", user.id)
    response = RedirectResponse("/", status_code=303)
    clear_session_cookie(response)
    clear_handshake_cookies(response)
    return response


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(request: Request) -> Response:
    """Clear the session cookie. CSRF-guarded: it changes auth state."""
    return await _logout(request)


@router.get("/logout")
async def logout_get(request: Request) -> Response:
    """GET fallback so a plain link can log out without JavaScript."""
    return await _logout(request)


# --- Small HTML responses for failure paths --------------------------------


def _error_page(message: str, status_code: int = 400) -> HTMLResponse:
    body = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ошибка входа — {settings.app_name}</title>
<style>
  body {{ background:#0b1020; color:#e8ecff; font-family:Inter,system-ui,sans-serif;
         display:flex; min-height:100vh; align-items:center; justify-content:center;
         margin:0; text-align:center; padding:24px; }}
  .card {{ background:#151b33; border:1px solid #26304f; border-radius:16px;
           padding:40px; max-width:460px; }}
  a {{ color:#7c9cff; }}
</style></head>
<body><div class="card">
  <h1>Не удалось войти</h1>
  <p>{message}</p>
  <p><a href="/">На главную</a> · <a href="/auth/login">Попробовать снова</a></p>
</div></body></html>"""
    return HTMLResponse(body, status_code=status_code)


def _config_error_page(message: str | None = None) -> HTMLResponse:
    text = message or (
        "Вход через Google не настроен. Укажите GOOGLE_CLIENT_ID и "
        "GOOGLE_CLIENT_SECRET в файле .env и перезапустите приложение."
    )
    return _error_page(text, status_code=503)
