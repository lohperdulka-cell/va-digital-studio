"""Tests for email+password, one-time-code and Telegram sign-in.

These exercise the real routes and the real database — no mocks.  The mailer
and the Telegram Bot API both fall back to logging when unconfigured, so the
tests observe their effects through the service layer and the rendered pages.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.security.csrf import CSRF_COOKIE_NAME
from app.security.passwords import hash_password
from app.security.sessions import SESSION_COOKIE_NAME
from app.services import login_codes, telegram
from app.services.accounts import (
    EmailTakenError,
    authenticate_password,
    register_with_password,
)

PASSWORD = "secret123"
EMAIL = "night@example.com"


def _csrf(client: TestClient) -> str:
    """Fetch a page first so the double-submit cookie exists, then read it."""
    client.get("/")
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token, "CSRF cookie was not issued"
    return token


# --- Password hashing ------------------------------------------------------


def test_password_hash_is_salted_and_verifies():
    from app.security.passwords import verify_password

    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second, "each hash must use a fresh salt"
    assert verify_password(PASSWORD, first)
    assert not verify_password("wrong", first)


def test_password_policy_rejects_weak_input():
    from app.security.passwords import PasswordPolicyError, validate_password

    for weak in ["short1", "alllettersonly", "12345678", "password"]:
        with pytest.raises(PasswordPolicyError):
            validate_password(weak)


# --- Registration ----------------------------------------------------------


def test_register_creates_account_and_signs_in(client, db):
    token = _csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "name": "Ночной Гость",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")

    user = db.scalar(select(User).where(User.email == EMAIL))
    assert user is not None
    assert user.has_password
    assert user.display_name == "Ночной Гость"
    assert user.password_hash and user.password_hash != PASSWORD


def test_register_rejects_duplicate_email(client, db, make_user):
    make_user(EMAIL)
    token = _csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "уже существует" in response.text


def test_register_rejects_mismatched_passwords(client):
    token = _csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "password_confirm": "different123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "не совпадают" in response.text


def test_register_rejects_bad_email(client):
    token = _csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "email": "not-an-email",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "e-mail" in response.text.lower()


def test_register_requires_csrf(client):
    client.get("/")
    response = client.post(
        "/auth/register",
        data={"email": EMAIL, "password": PASSWORD, "password_confirm": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 403


# --- Password sign-in ------------------------------------------------------


def test_login_with_password_succeeds(client, db):
    register_with_password(db, email=EMAIL, password=PASSWORD, name="Тест")
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={"email": EMAIL, "password": PASSWORD, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # Matches the Google flow: no explicit target lands on the profile page.
    assert response.headers["location"] == "/profile"
    assert SESSION_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_login_is_case_insensitive_for_email(client, db):
    register_with_password(db, email=EMAIL, password=PASSWORD)
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={"email": "NIGHT@Example.COM", "password": PASSWORD, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_login_with_wrong_password_is_rejected(client, db):
    register_with_password(db, email=EMAIL, password=PASSWORD)
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={"email": EMAIL, "password": "definitely-wrong", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Неверный e-mail или пароль" in response.text
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


def test_login_for_unknown_account_looks_the_same(client):
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={"email": "ghost@example.com", "password": PASSWORD, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "Неверный e-mail или пароль" in response.text


def test_login_honours_safe_next(client, db):
    register_with_password(db, email=EMAIL, password=PASSWORD)
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "next": "/profile",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"


def test_login_ignores_offsite_next(client, db):
    """An absolute URL must not become an open redirect."""
    register_with_password(db, email=EMAIL, password=PASSWORD)
    token = _csrf(client)
    response = client.post(
        "/auth/login",
        data={
            "email": EMAIL,
            "password": PASSWORD,
            "next": "https://evil.example.com",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"


def test_authenticate_password_returns_none_for_missing_user(db):
    assert authenticate_password(db, email="nobody@example.com", password="x") is None


def test_register_with_password_raises_on_taken_email(db):
    register_with_password(db, email=EMAIL, password=PASSWORD)
    with pytest.raises(EmailTakenError):
        register_with_password(db, email=EMAIL, password=PASSWORD)


# --- Telegram --------------------------------------------------------------


def test_telegram_page_hidden_when_unconfigured(client):
    response = client.get("/auth/telegram")
    assert response.status_code == 200
    assert "не настроен" in response.text


def test_telegram_flow_when_configured(monkeypatch, client, db):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:ABC")
    monkeypatch.setattr(settings, "telegram_bot_username", "va_studio_bot")
    token = _csrf(client)

    response = client.post(
        "/auth/telegram",
        data={"email": EMAIL, "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "t.me/va_studio_bot?start=" in response.text

    code = login_codes.issue_code(
        db, email=EMAIL, channel=login_codes.CHANNEL_TELEGRAM
    )
    verified = client.post(
        "/auth/telegram/verify",
        data={"email": EMAIL, "code": code, "csrf_token": token},
        follow_redirects=False,
    )
    assert verified.status_code == 303
    assert SESSION_COOKIE_NAME in verified.headers.get("set-cookie", "")


def test_telegram_code_is_not_valid_on_the_telegram_endpoint_after_use(
    client, db
):
    """A Telegram code is single-use: replaying it must be rejected."""
    token = _csrf(client)
    code = login_codes.issue_code(
        db, email=EMAIL, channel=login_codes.CHANNEL_TELEGRAM
    )
    first = client.post(
        "/auth/telegram/verify",
        data={"email": EMAIL, "code": code, "csrf_token": token},
        follow_redirects=False,
    )
    assert first.status_code == 303

    replay = client.post(
        "/auth/telegram/verify",
        data={"email": EMAIL, "code": code, "csrf_token": token},
        follow_redirects=False,
    )
    assert replay.status_code == 400


def test_start_payload_round_trips_the_email():
    payload = telegram.create_start_payload(EMAIL)
    assert telegram.read_start_payload(payload) == EMAIL


def test_start_payload_rejects_tampering():
    payload = telegram.create_start_payload(EMAIL)
    assert telegram.read_start_payload(payload[:-3] + "xyz") is None


def test_start_payload_ignores_a_session_token():
    """A session JWT must not be accepted as a Telegram start payload."""
    from app.security.tokens import create_session_token

    token, _ = create_session_token(user_id=1, email=EMAIL, is_admin=False)
    assert telegram.read_start_payload(token) is None


# --- Rate limiting ---------------------------------------------------------


def test_auth_paths_are_rate_limited():
    from app.security.ratelimit import _is_guarded

    assert _is_guarded("/auth/login")
    assert _is_guarded("/auth/register")
