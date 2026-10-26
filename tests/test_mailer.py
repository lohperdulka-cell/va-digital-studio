"""Tests for the outbound mailer's unconfigured-SMTP fallback.

The rule under test: without SMTP, development logs the message (so a
developer can read the code) while production refuses and never writes the
code to the deploy log.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.services import mailer

CODE = "999888"


def _unconfigure_mail(monkeypatch, env: str) -> None:
    monkeypatch.setattr(settings, "app_env", env)
    for field in ("email_host", "smtp_host", "email_user", "smtp_user"):
        monkeypatch.setattr(settings, field, "")
    for field in ("email_password", "smtp_password"):
        monkeypatch.setattr(settings, field, "")
    monkeypatch.setattr(settings, "email_api_provider", "")
    monkeypatch.setattr(settings, "email_api_key", "")


def test_production_does_not_leak_the_code_into_logs(monkeypatch, caplog):
    _unconfigure_mail(monkeypatch, "production")

    with caplog.at_level(logging.INFO):
        delivered = mailer.send_login_code(to_email="user@example.com", code=CODE)

    assert delivered is False
    assert CODE not in caplog.text
    assert "not sent" in caplog.text


def test_development_logs_the_code_for_debugging(monkeypatch, caplog):
    _unconfigure_mail(monkeypatch, "development")

    with caplog.at_level(logging.INFO):
        delivered = mailer.send_login_code(to_email="user@example.com", code=CODE)

    assert delivered is True
    assert CODE in caplog.text


def test_a_user_without_a_password_is_treated_as_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "email_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "email_user", "studio@example.com")
    monkeypatch.setattr(settings, "email_password", "")

    assert settings.email_configured is False


def test_host_user_and_password_together_are_configured(monkeypatch):
    monkeypatch.setattr(settings, "email_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "email_user", "studio@example.com")
    monkeypatch.setattr(settings, "email_password", "app-password")

    assert settings.email_configured is True


# --- HTTP API transport (the only option on Render's free plan) -------------


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


class _FakeClient:
    """Captures the request instead of hitting the network."""

    calls: list[tuple[str, dict, dict]] = []
    status_code = 200

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def post(self, url, headers=None, json=None):
        type(self).calls.append((url, headers or {}, json or {}))
        return _FakeResponse(type(self).status_code)


def test_api_transport_is_used_when_configured(monkeypatch):
    _unconfigure_mail(monkeypatch, "production")
    monkeypatch.setattr(settings, "email_api_provider", "resend")
    monkeypatch.setattr(settings, "email_api_key", "key-123")
    _FakeClient.calls = []
    monkeypatch.setattr(mailer.httpx, "Client", _FakeClient)

    delivered = mailer.send_login_code(to_email="user@example.com", code=CODE)

    assert delivered is True
    url, headers, payload = _FakeClient.calls[0]
    assert url == "https://api.resend.com/emails"
    assert headers["Authorization"] == "Bearer key-123"
    assert payload["to"] == ["user@example.com"]
    assert CODE in payload["subject"]


def test_brevo_api_shape(monkeypatch):
    _unconfigure_mail(monkeypatch, "production")
    monkeypatch.setattr(settings, "email_api_provider", "brevo")
    monkeypatch.setattr(settings, "email_api_key", "key-456")
    _FakeClient.calls = []
    monkeypatch.setattr(mailer.httpx, "Client", _FakeClient)

    assert mailer.send_login_code(to_email="user@example.com", code=CODE) is True

    url, headers, payload = _FakeClient.calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert headers["api-key"] == "key-456"
    assert payload["to"] == [{"email": "user@example.com"}]
    assert "textContent" in payload


def test_api_failure_is_reported_not_raised(monkeypatch):
    _unconfigure_mail(monkeypatch, "production")
    monkeypatch.setattr(settings, "email_api_provider", "resend")
    monkeypatch.setattr(settings, "email_api_key", "key-123")
    _FakeClient.calls = []
    _FakeClient.status_code = 500
    monkeypatch.setattr(mailer.httpx, "Client", _FakeClient)

    try:
        assert mailer.send_login_code(to_email="user@example.com", code=CODE) is False
    finally:
        _FakeClient.status_code = 200


def test_unknown_api_provider_fails_cleanly(monkeypatch, caplog):
    _unconfigure_mail(monkeypatch, "production")
    monkeypatch.setattr(settings, "email_api_provider", "sendgrid")
    monkeypatch.setattr(settings, "email_api_key", "key-789")

    with caplog.at_level(logging.INFO):
        delivered = mailer.send_login_code(to_email="user@example.com", code=CODE)

    assert delivered is False
    assert CODE not in caplog.text


def test_api_configuration_alone_marks_email_configured(monkeypatch):
    _unconfigure_mail(monkeypatch, "production")
    monkeypatch.setattr(settings, "email_api_provider", "resend")
    monkeypatch.setattr(settings, "email_api_key", "key-123")

    assert settings.email_configured is True
