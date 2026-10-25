"""Tests for the per-IP rate limiter."""

from __future__ import annotations

import pytest

from app.security import ratelimit
from app.security.ratelimit import RateLimiter, _is_guarded


@pytest.fixture(autouse=True)
def _restore_limiter_settings():
    """Tests mutate the module-level limit; put it back afterwards.

    Bucket clearing between tests is handled by the shared conftest fixture.
    """
    original_limit = ratelimit.limiter.limit
    original_window = ratelimit.limiter.window_seconds
    yield
    ratelimit.limiter.limit = original_limit
    ratelimit.limiter.window_seconds = original_window


def test_guarded_paths_are_the_sensitive_ones():
    assert _is_guarded("/auth/login")
    assert _is_guarded("/auth/callback")
    assert _is_guarded("/support")
    assert _is_guarded("/contact")


def test_public_and_dashboard_paths_are_not_guarded():
    for path in ("/", "/catalog", "/news", "/dashboard/orders", "/static/app.css"):
        assert not _is_guarded(path), path


def test_counter_allows_up_to_the_limit_then_refuses():
    limiter = RateLimiter(limit=3, window_seconds=60)
    results = [limiter.check("1.2.3.4")[0] for _ in range(4)]
    assert results == [True, True, True, False]


def test_remaining_decreases_and_never_goes_negative():
    limiter = RateLimiter(limit=2, window_seconds=60)
    remaining = [limiter.check("1.2.3.4")[1] for _ in range(4)]
    assert remaining == [1, 0, 0, 0]


def test_buckets_are_isolated_per_key():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is False
    assert limiter.check("b")[0] is True


def test_window_resets_after_it_expires():
    limiter = RateLimiter(limit=1, window_seconds=0)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is True  # a zero-length window has elapsed


def test_middleware_returns_429_with_retry_after(client):
    """A guarded path answers 429 once the budget is spent."""
    ratelimit.limiter.limit = 2
    ratelimit.limiter._buckets.clear()

    statuses = [client.get("/support").status_code for _ in range(3)]

    assert statuses[:2] != [429, 429]
    assert statuses[2] == 429

    throttled = client.get("/support")
    assert throttled.status_code == 429
    assert int(throttled.headers["retry-after"]) > 0
    assert throttled.headers["x-ratelimit-remaining"] == "0"


def test_middleware_leaves_public_paths_alone(client):
    ratelimit.limiter.limit = 1
    ratelimit.limiter._buckets.clear()

    statuses = [client.get("/catalog").status_code for _ in range(5)]

    assert 429 not in statuses
