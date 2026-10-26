"""VA Digital Studio — FastAPI application entry point.

Step 2 wires up logging, the database, the session/JWT authentication stack and
global error handling.  Page routers are mounted incrementally in later steps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import engine
from app.errors import AppError, NotAuthenticatedError, wants_json
from app.logging_config import get_logger, setup_logging
from app.middleware import CurrentUserMiddleware
from app.routes import admin as admin_routes
from app.routes import auth as auth_routes
from app.routes import chat as chat_routes
from app.routes import faq as faq_routes
from app.routes import login as login_routes
from app.routes import news as news_routes
from app.routes import pages as page_routes
from app.routes import portfolio as portfolio_routes
from app.routes import profile as profile_routes
from app.routes import reviews as review_routes
from app.routes import services as service_routes
from app.security.csrf import CsrfCookieMiddleware
from app.security.headers import SecurityHeadersMiddleware
from app.security.ratelimit import RateLimitMiddleware
from app.seed import bootstrap as bootstrap_content
from app.templating import STATIC_DIR, render

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    logger.info(
        "Starting %s (env=%s, db=%s, oauth=%s)",
        settings.app_name,
        settings.app_env,
        "sqlite" if settings.is_sqlite else "postgresql",
        "configured" if settings.oauth_configured else "NOT configured",
    )
    if not settings.oauth_configured:
        logger.warning(
            "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are unset — the Google "
            "button is hidden. Email+password and Telegram sign-in still work."
        )
    elif settings.base_url_is_local and settings.is_production:
        # The single most common misconfiguration: BASE_URL still points at
        # localhost, so Google is handed a redirect_uri it cannot call back.
        logger.warning(
            "BASE_URL is %s in production — Google will reject the redirect. "
            "Set BASE_URL (or rely on RENDER_EXTERNAL_URL). Redirect URI: %s",
            settings.base_url,
            settings.google_redirect_uri,
        )

    # start.sh already bootstraps; this covers hosts that run the ASGI app
    # directly (e.g. a dashboard Start Command of `gunicorn app.main:app`), where
    # start.sh never executes.  Both paths are idempotent, and the seeding step
    # only touches an empty catalogue.  Never fatal: a content problem must not
    # stop the site from serving.  Skipped under APP_ENV=test so the suite keeps
    # controlling its own fixtures.
    if settings.app_env.lower() not in {"test", "testing"}:
        try:
            bootstrap_content()
        except Exception:
            logger.exception("Content bootstrap failed — continuing without it")

    yield
    engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware runs bottom-up: SessionMiddleware must wrap the OAuth handshake
# state, CsrfCookieMiddleware issues the CSRF cookie, CurrentUserMiddleware
# resolves our own JWT session cookie, RateLimitMiddleware throttles the
# sensitive paths, and SecurityHeadersMiddleware stamps the hardening headers
# on the outermost layer so they survive every response.
app.add_middleware(CurrentUserMiddleware)
app.add_middleware(CsrfCookieMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="va_oauth_session",
    max_age=600,  # the OAuth round-trip only needs a few minutes
    same_site="lax",
    https_only=settings.cookie_secure,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth_routes.router)
app.include_router(login_routes.router)
app.include_router(page_routes.router)
app.include_router(service_routes.router)
app.include_router(news_routes.router)
app.include_router(portfolio_routes.router)
app.include_router(review_routes.router)
app.include_router(faq_routes.router)
app.include_router(profile_routes.router)
app.include_router(chat_routes.router)
app.include_router(admin_routes.router)


# --- Error handling --------------------------------------------------------


def _render_error(request: Request, exc: AppError) -> HTMLResponse | JSONResponse:
    if wants_json(request):
        return JSONResponse(
            {"error": exc.title, "detail": exc.detail}, status_code=exc.status_code
        )
    try:
        return render(
            request,
            "errors/error.html",
            {"status_code": exc.status_code, "title": exc.title, "detail": exc.detail},
            status_code=exc.status_code,
        )
    except Exception:  # noqa: BLE001 - an error page must never raise itself
        # Never let an error page itself raise.
        return HTMLResponse(
            f"<h1>{exc.status_code} — {exc.title}</h1><p>{exc.detail}</p>"
            '<p><a href="/">На главную</a></p>',
            status_code=exc.status_code,
        )


def not_authenticated_response(
    request: Request, exc: NotAuthenticatedError
) -> HTMLResponse | JSONResponse | RedirectResponse:
    """AJAX callers get a 401 with a login URL; browsers get sent to Google."""
    if wants_json(request):
        return JSONResponse(
            {"error": exc.title, "detail": exc.detail, "login_url": "/auth/login"},
            status_code=exc.status_code,
        )
    # Remember where the visitor wanted to go so we can return them there.
    # For a POST there is nothing to return to (the route is not a page), so
    # land on the home page after logging in instead of a 405.
    if request.method in {"GET", "HEAD"}:
        target = request.url.path
        if request.url.query:
            target = f"{target}?{request.url.query}"
    else:
        target = "/"
    return RedirectResponse(f"/auth/login?next={target}", status_code=303)


def render_app_error(request: Request, exc: AppError):
    return _render_error(request, exc)


def unhandled_error_response(request: Request, exc: Exception):
    """Log the detail, return a generic message — never leak internals."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    if wants_json(request):
        return JSONResponse(
            {"error": "Внутренняя ошибка", "detail": "Мы уже разбираемся"},
            status_code=500,
        )
    return HTMLResponse(
        "<h1>500 — Внутренняя ошибка сервера</h1>"
        "<p>Мы уже разбираемся. Попробуйте обновить страницу позже.</p>"
        '<p><a href="/">На главную</a></p>',
        status_code=500,
    )


def register_error_handlers(target: FastAPI) -> None:
    """Attach the standard handlers — also used by test apps in ``tests/``."""

    @target.exception_handler(NotAuthenticatedError)
    async def _not_authenticated(request: Request, exc: NotAuthenticatedError):
        return not_authenticated_response(request, exc)

    @target.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return render_app_error(request, exc)

    @target.exception_handler(Exception)
    async def _unhandled_error(request: Request, exc: Exception):
        return unhandled_error_response(request, exc)


register_error_handlers(app)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Liveness probe used by docker-compose and the load balancer."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}
