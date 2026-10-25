"""Google OAuth 2.0 client built on authlib.

authlib is imported lazily inside :func:`get_oauth` so the application still
boots (and tests still run) when no Google credentials are configured.
"""

from __future__ import annotations

from typing import Any

from app.config import settings

_cache_key: tuple[str, str] | None = None
_oauth: Any | None = None


def get_oauth() -> Any | None:
    """Return the configured OAuth registry, or ``None`` if not set up.

    The registry is cached but the cache is invalidated when the client
    credentials change, so picking up new configuration does not require a
    process restart.
    """
    global _oauth, _cache_key

    key = (settings.google_client_id, settings.google_client_secret)
    if _oauth is not None and _cache_key == key:
        return _oauth
    if not settings.oauth_configured:
        _oauth = None
        _cache_key = key
        return None

    from authlib.integrations.starlette_client import OAuth

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=settings.google_discovery_url,
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        },
    )
    _oauth = oauth
    _cache_key = key
    return _oauth
