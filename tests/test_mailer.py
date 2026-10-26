"""Tests for the outbound mailer's unconfigured-SMTP fallback.

The rule under test: without SMTP, development logs the message (so a
developer can read the code) while production refuses and never writes the
code to the deploy log.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.services import mailer

CODE = "999888"


def _unconfigure_smtp(monkeypatch, env: str) -> None:
    monkeypatch.setattr(settings, "app_env", env)
    for field in ("email_host", "smtp_host", "email_user", "smtp_user"):
        monkeypatch.setattr(settings, field, "")
    for field in ("email_password", "smtp_password"):
        monkeypatch.setattr(settings, field, "")


def test_production_does_not_leak_the_code_into_logs(monkeypatch, caplog):
    _unconfigure_smtp(monkeypatch, "production")

    with caplog.at_level(logging.INFO):
        delivered = mailer.send_login_code(to_email="user@example.com", code=CODE)

    assert delivered is False
    assert CODE not in caplog.text
    assert "not configured" in caplog.text


def test_development_logs_the_code_for_debugging(monkeypatch, caplog):
    _unconfigure_smtp(monkeypatch, "development")

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
