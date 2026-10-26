"""Shared pytest fixtures.

Each test module gets an isolated SQLite database created from the ORM
metadata, so the suite never touches the development database.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Configure the environment before app.config is imported anywhere.
# Environment variables outrank the developer's `.env`, so the suite is
# deterministic even when a real `.env` is present.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="va-studio-tests-"))
os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = "test-" + "0" * 64
os.environ["SQLITE_PATH"] = str(_TMP_DIR / "test.db")
# A DATABASE_URL from the surrounding shell would silently outrank the test
# SQLite file and point the suite at a real database.
os.environ["DATABASE_URL"] = ""
os.environ["LOG_DIR"] = str(_TMP_DIR / "logs")
os.environ["ADMIN_EMAILS"] = "boss@example.com"
os.environ["COOKIE_SECURE"] = "false"
# Pinned so a RENDER_EXTERNAL_URL inherited from a deployment shell cannot
# change the redirect URI the OAuth tests assert on.
os.environ["BASE_URL"] = "http://localhost:8000"
os.environ["RENDER_EXTERNAL_URL"] = ""
# OAuth is unconfigured by default; the tests that need it opt in explicitly.
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security.sessions import SESSION_COOKIE_NAME
from app.security.tokens import create_session_token


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    """Truncate every table between tests for deterministic ordering."""
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Clear the in-process limiters so counts never bleed between tests."""
    from app.routes import chat as chat_routes
    from app.security import ratelimit

    ratelimit.limiter._buckets.clear()
    chat_routes._chat_limiter._buckets.clear()
    yield
    ratelimit.limiter._buckets.clear()
    chat_routes._chat_limiter._buckets.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def smtp_configured(monkeypatch):
    """Make the app believe SMTP is set up, without touching the network.

    The behaviour under test is the route's honest-flag logic, so only the
    final SMTP hop is replaced; the configuration checks, the mailer and the
    templates all run for real.
    """
    from app.config import settings
    from app.services import mailer

    monkeypatch.setattr(settings, "email_host", "smtp.example.com")
    monkeypatch.setattr(settings, "email_user", "studio@example.com")
    monkeypatch.setattr(settings, "email_password", "app-password")
    monkeypatch.setattr(mailer, "_deliver", lambda **_kwargs: True)
    return mailer


@pytest.fixture
def make_user(db: Session):
    """Factory creating a persisted user with an optional admin flag."""

    def _make(
        email: str = "user@example.com",
        *,
        is_admin: bool = False,
        google_id: str | None = None,
        name: str = "Test User",
    ) -> User:
        user = User(
            google_id=google_id or f"google-{email}",
            email=email,
            name=name,
            is_admin=is_admin,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def login_as(client: TestClient):
    """Attach a valid session cookie for the given user."""

    def _login(user: User) -> TestClient:
        token, _expires = create_session_token(
            user_id=user.id, email=user.email, is_admin=user.is_admin
        )
        client.cookies.set(SESSION_COOKIE_NAME, token)
        return client

    return _login
