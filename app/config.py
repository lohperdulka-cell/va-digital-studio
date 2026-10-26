"""Application settings, loaded from environment / `.env` via pydantic-settings."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

_INSECURE_SECRET_PREFIXES = ("change-me", "secret", "changeme")

# Both of these appear in the wild as `DATABASE_URL`.  `postgres://` is the
# legacy Heroku/Render form, `postgresql://` the modern one; SQLAlchemy needs a
# driver suffix on either.
_BARE_POSTGRES_SCHEMES = ("postgres://", "postgresql://")
_POSTGRES_DRIVER = "postgresql+psycopg2://"


class Settings(BaseSettings):
    """Typed, validated view over the process environment."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "VA Digital Studio"
    app_env: str = "development"
    debug: bool = True
    # Empty means "work it out": RENDER_EXTERNAL_URL if present, else localhost.
    base_url: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    # Injected automatically by Render; used to derive BASE_URL so the OAuth
    # redirect URI matches the deployed host without manual configuration.
    render_external_url: str = ""

    # --- Database ----------------------------------------------------------
    database_url: str = ""
    # Kept inside ./data so the SQLite fallback lands in the directory the
    # Dockerfile makes writable for the unprivileged runtime user.  The
    # application root itself stays read-only in the image.
    sqlite_path: str = "./data/va_studio.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    # Cloud proxies drop idle connections; recycle well before that happens.
    db_pool_recycle: int = 1800

    # --- Secrets -----------------------------------------------------------
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "va-digital-studio"
    jwt_expire_days: int = 7
    # None -> resolved in _finalise: secure unless explicitly disabled.
    cookie_secure: bool | None = None

    # --- Google OAuth ------------------------------------------------------
    google_client_id: str = ""
    google_client_secret: str = ""
    google_discovery_url: str = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )

    # --- Administration ----------------------------------------------------
    admin_emails: str = ""

    # --- Logging -----------------------------------------------------------
    log_dir: str = "./logs"
    log_level: str = "INFO"
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5

    # --- Rate limiting -----------------------------------------------------
    # Requests allowed per window, per client IP, on sensitive endpoints.
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    # --- Support -----------------------------------------------------------
    support_email: str = "ethernallhatred@gmail.com"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # --- Outbound e-mail (preferred names) ---------------------------------
    # EMAIL_* wins over SMTP_* when both are set, so a host that documents one
    # naming scheme still works with the other.
    email_host: str = ""
    email_port: int = 587
    email_user: str = ""
    email_password: str = ""
    email_use_tls: bool = True
    email_from: str = ""

    # --- Telegram login ----------------------------------------------------
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""

    # --- Password / one-time code login ------------------------------------
    password_min_length: int = 8
    # A 6-digit code is valid for 10 minutes (requirement 1.2).
    login_code_ttl_seconds: int = 600
    # Wrong guesses allowed per code before it is burned.
    login_code_max_attempts: int = 5

    @field_validator("secret_key")
    @classmethod
    def _validate_secret_key(cls, value: str) -> str:
        if value and len(value) < 64:
            raise ValueError("SECRET_KEY must be at least 64 characters long")
        return value

    @staticmethod
    def _is_local(url: str) -> bool:
        """True for a URL that cannot be reached from the public internet."""
        host = (urlparse(url).hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(
            ".local"
        )

    @model_validator(mode="after")
    def _finalise(self) -> Settings:
        # Development convenience: generate an ephemeral key instead of refusing
        # to boot.  Production must supply a real one.
        if not self.secret_key or self.secret_key.startswith(_INSECURE_SECRET_PREFIXES):
            if self.is_production:
                raise ValueError(
                    "SECRET_KEY must be set to a strong random value in production"
                )
            self.secret_key = secrets.token_urlsafe(64)

        # Render exposes the public origin here.  An explicit BASE_URL always
        # wins (tests and custom domains rely on that); this only fills the gap
        # when it is unset, so the OAuth redirect URI is right by default.
        if not self.base_url and self.render_external_url:
            self.base_url = self.render_external_url.rstrip("/")
        if not self.base_url:
            self.base_url = f"http://localhost:{self.port}"

        # Production is HTTPS by definition, so a Secure cookie is the safe
        # default.  An explicit COOKIE_SECURE always wins (needed for a
        # plain-HTTP smoke test against a production build).
        if self.cookie_secure is None:
            self.cookie_secure = self.is_production

        return self

    # --- Derived helpers ---------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def admin_email_list(self) -> list[str]:
        """ADMIN_EMAILS as a normalised list of lower-case addresses."""
        return [
            email.strip().lower()
            for email in self.admin_emails.replace(";", ",").split(",")
            if email.strip()
        ]

    @property
    def normalized_database_url(self) -> str:
        """DATABASE_URL with an explicit SQLAlchemy driver.

        Providers hand out a bare ``postgres://`` or ``postgresql://`` URL.
        SQLAlchemy 2.x rejects ``postgres://`` outright and resolves a bare
        ``postgresql://`` to psycopg2, so pin the driver instead of relying on
        whatever happens to be installed.  An already-qualified URL such as
        ``postgresql+psycopg://`` is passed through untouched.
        """
        url = self.database_url.strip()
        for scheme in _BARE_POSTGRES_SCHEMES:
            if url.startswith(scheme):
                return _POSTGRES_DRIVER + url[len(scheme) :]
        return url

    @property
    def sqlalchemy_url(self) -> str:
        """Explicit DATABASE_URL wins; otherwise use the local SQLite file."""
        if self.database_url:
            return self.normalized_database_url
        path = Path(self.sqlite_path)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        return f"sqlite+pysqlite:///{path}"

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def log_path(self) -> Path:
        path = Path(self.log_dir)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/callback"

    @property
    def base_url_is_local(self) -> bool:
        """True when the OAuth redirect URI points somewhere unreachable."""
        return self._is_local(self.base_url)

    @property
    def oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def resolved_email_host(self) -> str:
        """EMAIL_HOST, falling back to the older SMTP_HOST."""
        return (self.email_host or self.smtp_host).strip()

    @property
    def resolved_email_port(self) -> int:
        return int(self.email_port or self.smtp_port or 587)

    @property
    def resolved_email_user(self) -> str:
        return (self.email_user or self.smtp_user).strip()

    @property
    def resolved_email_password(self) -> str:
        return self.email_password or self.smtp_password

    @property
    def resolved_email_from(self) -> str:
        """Sender address; falls back to the SMTP user, then support_email."""
        return (
            self.email_from or self.resolved_email_user or self.support_email
        ).strip()

    @property
    def email_configured(self) -> bool:
        """True when a code can actually be delivered.

        A username without a password cannot authenticate, so it counts as
        unconfigured: the sign-in page then tells the visitor the truth instead
        of failing at send time.
        """
        if not (self.resolved_email_host and self.resolved_email_from):
            return False
        if self.resolved_email_user and not self.resolved_email_password:
            return False
        return True

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
