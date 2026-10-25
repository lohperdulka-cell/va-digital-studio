"""Tests for the authentication stack: JWT, sessions, middleware, OAuth state."""

from __future__ import annotations

import datetime

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.main import register_error_handlers
from app.middleware import CurrentUserMiddleware
from app.security.sessions import (
    SESSION_COOKIE_NAME,
    get_current_admin,
    get_current_user,
)
from app.security.tokens import (
    create_session_token,
    create_state_token,
    decode_session_token,
    decode_state_token,
    safe_next_path,
)
from app.services.accounts import (
    OAuthProfileError,
    profile_from_id_token,
    upsert_user,
)

# --- Token tests -----------------------------------------------------------


def test_session_token_round_trip():
    token, expires_at = create_session_token(
        user_id=42, email="a@b.c", is_admin=True
    )
    claims = decode_session_token(token)
    assert claims is not None
    assert claims["sub"] == "42"
    assert claims["email"] == "a@b.c"
    assert claims["adm"] is True
    assert claims["iss"] == settings.jwt_issuer
    assert expires_at > datetime.datetime.now(datetime.UTC)


def test_tampered_signature_is_rejected():
    token, _ = create_session_token(user_id=1, email="a@b.c", is_admin=False)
    assert decode_session_token(token[:-4] + "AAAA") is None


def test_expired_token_is_rejected():
    now = datetime.datetime.now(datetime.UTC)
    past = now - datetime.timedelta(days=1)
    expired = jwt.encode(
        {
            "sub": "1",
            "typ": "session",
            "iss": settings.jwt_issuer,
            "iat": past,
            "exp": past,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_session_token(expired) is None


def test_wrong_issuer_is_rejected():
    now = datetime.datetime.now(datetime.UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "typ": "session",
            "iss": "somebody-else",
            "iat": now,
            "exp": now + datetime.timedelta(hours=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_session_token(token) is None


def test_state_token_is_not_usable_as_a_session():
    state, _nonce = create_state_token("/profile")
    assert decode_state_token(state) is not None
    assert decode_session_token(state) is None


def test_signed_token_without_expiry_is_rejected():
    """`exp` is a required claim — omitting it must fail closed."""
    token = jwt.encode(
        {"sub": "1", "typ": "session", "iss": settings.jwt_issuer},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_session_token(token) is None


# --- Redirect safety -------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    ["//evil.com", "https://evil.com", "http://evil.com/x", "/\\evil", "", None],
)
def test_open_redirects_are_blocked(hostile):
    assert safe_next_path(hostile) == "/profile"


@pytest.mark.parametrize("allowed", ["/profile", "/catalog/python-bots", "/ok?a=1"])
def test_relative_paths_are_allowed(allowed):
    assert safe_next_path(allowed) == allowed


# --- Profile normalisation -------------------------------------------------


def test_profile_is_normalised():
    profile = profile_from_id_token(
        {
            "sub": "123",
            "email": "Mixed@Case.COM",
            "name": "  Ivan  ",
            "picture": "https://img/avatar.png",
            "email_verified": True,
        }
    )
    assert profile == {
        "google_id": "123",
        "email": "mixed@case.com",
        "name": "Ivan",
        "avatar_url": "https://img/avatar.png",
    }


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "a@b.c"},
        {"sub": "1"},
        {"sub": "1", "email": "a@b.c", "email_verified": False},
        {"sub": "1", "email": "   "},
    ],
)
def test_bad_profiles_are_rejected(claims):
    with pytest.raises(OAuthProfileError):
        profile_from_id_token(claims)


# --- Account provisioning --------------------------------------------------


def test_upsert_is_idempotent(db):
    profile = {
        "google_id": "g-1",
        "email": "user@example.com",
        "name": "First",
        "avatar_url": None,
    }
    user, created = upsert_user(db, profile)
    assert created is True

    again, created_again = upsert_user(db, dict(profile, name="Second"))
    assert created_again is False
    assert again.id == user.id
    assert again.name == "Second"


def test_upsert_adopts_row_by_email_when_google_id_changes(db):
    first, _ = upsert_user(
        db,
        {"google_id": "g-old", "email": "same@example.com", "name": "A", "avatar_url": None},
    )
    second, created = upsert_user(
        db,
        {"google_id": "g-new", "email": "same@example.com", "name": "A", "avatar_url": None},
    )
    assert created is False
    assert second.id == first.id
    assert second.google_id == "g-new"


def test_admin_emails_promotes_on_login(db):
    """ADMIN_EMAILS is applied on every login (requirement 4.1)."""
    user, _ = upsert_user(
        db,
        {
            "google_id": "g-boss",
            "email": "boss@example.com",
            "name": "Boss",
            "avatar_url": None,
        },
    )
    assert user.is_admin is True

    plain, _ = upsert_user(
        db,
        {
            "google_id": "g-plain",
            "email": "plain@example.com",
            "name": "Plain",
            "avatar_url": None,
        },
    )
    assert plain.is_admin is False


# --- Middleware and dependencies ------------------------------------------


def _probe_app() -> FastAPI:
    """The real middleware, the real error handlers, and protected probe routes.

    Assertions here therefore exercise the same code paths as the application.
    """
    probe = FastAPI()
    probe.add_middleware(CurrentUserMiddleware)
    register_error_handlers(probe)

    @probe.get("/whoami")
    def whoami(user=Depends(get_current_user)):  # noqa: B008
        return {"id": user.id, "email": user.email}

    @probe.get("/admin-only")
    def admin_only(user=Depends(get_current_admin)):  # noqa: B008
        return {"id": user.id}

    return probe


def test_middleware_populates_request_state(db, make_user):
    user = make_user("state@example.com")
    token, _ = create_session_token(
        user_id=user.id, email=user.email, is_admin=user.is_admin
    )
    with TestClient(_probe_app()) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/whoami")
    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": user.email}


def test_missing_session_redirects_browsers_to_login(db):
    """A browser (HTML Accept) is sent to the login page, not shown a 401."""
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        response = client.get("/whoami", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login?next=")


def test_missing_session_returns_json_for_api_clients(db):
    """An API caller gets a machine-readable 401 with the login URL."""
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        response = client.get(
            "/whoami",
            headers={"accept": "application/json"},
            follow_redirects=False,
        )
    assert response.status_code == 401
    assert response.json()["login_url"] == "/auth/login"


def test_redirect_preserves_the_requested_path(db):
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        response = client.get("/admin-only", follow_redirects=False)
    assert response.headers["location"] == "/auth/login?next=/admin-only"


def test_invalid_session_cookie_is_rejected(db):
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-jwt")
        response = client.get("/whoami", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/auth/login")


def test_session_for_deleted_user_is_rejected(db, make_user):
    user = make_user("ghost@example.com")
    token, _ = create_session_token(
        user_id=user.id, email=user.email, is_admin=False
    )
    db.delete(user)
    db.commit()
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/whoami", follow_redirects=False)
    assert response.status_code == 303


def test_admin_route_allows_admin_and_blocks_regular_user(db, make_user):
    admin = make_user("root@example.com", is_admin=True)
    regular = make_user("pleb@example.com", is_admin=False)

    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        token, _ = create_session_token(
            user_id=admin.id, email=admin.email, is_admin=True
        )
        client.cookies.set(SESSION_COOKIE_NAME, token)
        assert client.get("/admin-only").status_code == 200

        client.cookies.clear()
        token, _ = create_session_token(
            user_id=regular.id, email=regular.email, is_admin=False
        )
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/admin-only", follow_redirects=False)
    # A logged-in non-admin is refused outright, not redirected to log in.
    assert response.status_code == 403


def test_admin_route_returns_403_json_for_api_clients(db, make_user):
    regular = make_user("pleb2@example.com", is_admin=False)
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        token, _ = create_session_token(
            user_id=regular.id, email=regular.email, is_admin=False
        )
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/admin-only", headers={"accept": "application/json"})
    assert response.status_code == 403
    assert response.json()["error"] == "Доступ запрещён"


def test_inactive_user_session_is_rejected(db, make_user):
    user = make_user("blocked@example.com")
    user.is_active = False
    db.commit()
    token, _ = create_session_token(
        user_id=user.id, email=user.email, is_admin=False
    )
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/whoami", follow_redirects=False)
    assert response.status_code == 303


# --- OAuth routes ----------------------------------------------------------


def test_login_without_credentials_shows_configuration_error(client):
    response = client.get("/auth/login", follow_redirects=False)
    assert response.status_code == 503
    assert "не настроен" in response.text


def test_callback_without_state_is_refused(client):
    response = client.get("/auth/callback?code=abc&state=forged")
    assert response.status_code == 400
    assert "Проверка безопасности не пройдена" in response.text


def test_callback_with_mismatched_state_is_refused(client):
    state, _ = create_state_token("/profile")
    client.cookies.set("va_oauth_state", "a-different-value")
    response = client.get(f"/auth/callback?code=abc&state={state}")
    assert response.status_code == 400


def test_callback_with_oauth_error_is_handled(client):
    response = client.get("/auth/callback?error=access_denied")
    assert response.status_code == 400
    assert "отменён" in response.text


def test_logout_requires_csrf_token(client, db, make_user, login_as):
    """Logout changes auth state, so it is CSRF-guarded (step 6)."""
    user = make_user("csrf-bye@example.com")
    login_as(user)

    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 403
    # The session survives the rejected request.
    assert client.cookies.get(SESSION_COOKIE_NAME)


def test_logout_clears_the_session_cookie(client, db, make_user, login_as):
    from app.security.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

    user = make_user("bye@example.com")
    login_as(user)
    assert client.cookies.get(SESSION_COOKIE_NAME)

    client.get("/")  # issue the CSRF cookie
    token = client.cookies.get(CSRF_COOKIE_NAME)

    response = client.post(
        "/auth/logout",
        headers={CSRF_HEADER_NAME: token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    # The Set-Cookie header must expire the session cookie.
    assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_logout_get_fallback_works_for_plain_links(client, db, make_user, login_as):
    """A GET logout link keeps working without JavaScript (no CSRF needed)."""
    user = make_user("link-bye@example.com")
    login_as(user)

    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_healthz_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_cookie_flags(db, make_user):
    """httponly + samesite=lax are always set; secure follows COOKIE_SECURE."""
    from fastapi import Response

    from app.security.sessions import issue_session

    user = make_user("cookie@example.com")
    response = Response()
    issue_session(response, user)
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "samesite=lax" in header.lower()


def test_configured_oauth_builds_a_real_google_authorize_url(monkeypatch, client):
    """With credentials present the redirect really points at Google.

    authlib assembles the authorize URL from local configuration, so this
    exercises the production code path without any network access.
    """
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")

    response = client.get("/auth/login?next=/profile", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in location
    assert "code_challenge_method=S256" in location
    assert "code_challenge=" in location
    assert "state=" in location
    assert "scope=openid" in location
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback" in location

    # The double-submit state cookie must accompany the redirect.
    assert "va_oauth_state" in response.headers.get("set-cookie", "")


def test_state_cookie_matches_the_state_sent_to_google(monkeypatch, client):
    """The state in the URL and in the cookie must be byte-identical."""
    from app.security.sessions import STATE_COOKIE_NAME

    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")

    response = client.get("/auth/login", follow_redirects=False)
    url_state = response.headers["location"].split("state=")[1].split("&")[0]
    cookie_state = client.cookies.get(STATE_COOKIE_NAME)

    assert cookie_state is not None
    assert cookie_state == url_state
