"""Tests for shared presentation helpers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.formatting import format_money


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("52500.00"), "52 500 ₽"),
        (Decimal(75000), "75 000 ₽"),
        (Decimal(0), "0 ₽"),
        (Decimal("1234567.50"), "1 234 567,50 ₽"),
        (Decimal("999.99"), "999,99 ₽"),
        (Decimal(1000000), "1 000 000 ₽"),
    ],
)
def test_format_money_uses_russian_conventions(value, expected):
    """Whole amounts drop the decimals; the rest use a comma separator."""
    assert format_money(value) == expected


def test_format_money_renders_none_as_dash():
    assert format_money(None) == "—"


def test_format_money_accepts_floats_and_strings():
    assert format_money(3000.0) == "3 000 ₽"
    assert format_money("2500") == "2 500 ₽"


def test_format_money_supports_a_prefix():
    assert format_money(Decimal(30000), prefix="от ") == "от 30 000 ₽"


def test_format_money_rejects_unparseable_values():
    assert format_money("не число") == "—"
