"""Cost calculator: pricing rules and the page/form round-trip."""

from __future__ import annotations

from decimal import Decimal

from app.services import estimator as estimator_service


def test_estimate_uses_base_price_and_days():
    result = estimator_service.estimate(
        project_type="landing", scope="basic", deadline="relaxed"
    )
    assert result.price_low < result.price_high
    assert result.days >= 1
    # Base single-page price is 500, range brackets it.
    assert result.price_low <= Decimal("500") <= result.price_high


def test_entry_and_top_prices_bracket_the_offer():
    """The catalogue runs from a 500 ₽ single page to a 5,000 ₽ multi-page site."""
    cheap = estimator_service.estimate(
        project_type="landing", scope="basic", deadline="relaxed"
    )
    rich = estimator_service.estimate(
        project_type="corporate", scope="basic", deadline="relaxed"
    )
    assert cheap.price_low <= Decimal("500") <= cheap.price_high
    assert rich.price_low <= Decimal("5000") <= rich.price_high


def test_scope_and_deadline_raise_the_price():
    cheap = estimator_service.estimate(
        project_type="landing", scope="basic", deadline="relaxed"
    )
    expensive = estimator_service.estimate(
        project_type="landing", scope="extended", deadline="urgent"
    )
    assert expensive.price_low > cheap.price_low


def test_addons_add_price_and_days():
    plain = estimator_service.estimate(project_type="bot", scope="basic", deadline="relaxed")
    with_addons = estimator_service.estimate(
        project_type="bot",
        scope="basic",
        deadline="relaxed",
        addons=["content", "support"],
    )
    assert with_addons.price_low > plain.price_low
    assert with_addons.days > plain.days


def test_unknown_keys_fall_back_instead_of_raising():
    result = estimator_service.estimate(
        project_type="nonsense", scope="nope", deadline="never", addons=["ghost"]
    )
    assert result.price_low > 0
    assert result.days >= 1


def test_urgent_deadline_shortens_the_timeline():
    relaxed = estimator_service.estimate(
        project_type="corporate", scope="standard", deadline="relaxed"
    )
    urgent = estimator_service.estimate(
        project_type="corporate", scope="standard", deadline="urgent"
    )
    assert urgent.days < relaxed.days


def test_calculator_page_renders(client):
    response = client.get("/calculator")
    assert response.status_code == 200
    assert "Примерная стоимость" in response.text


def test_calculator_post_returns_estimate(client):
    client.get("/")
    token = client.cookies.get("va_csrf")
    response = client.post(
        "/calculator",
        data={
            "project_type": "bot",
            "scope": "extended",
            "deadline": "urgent",
            "addons": ["integrations"],
            "csrf_token": token,
        },
    )
    assert response.status_code == 200
    assert "Примерная стоимость" in response.text
