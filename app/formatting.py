"""Presentation helpers shared by models, services and Jinja filters.

Money is the only thing here so far: it is rendered in templates, in chat
messages written by the service layer, and by ``price_display`` properties on
the models.  Keeping one implementation stops the three of them from drifting
into different formats for the same value.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def format_money(value: Decimal | float | None, *, prefix: str = "") -> str:
    """Render a rouble amount the Russian way: ``52 500 ₽``.

    Thousands are separated by a thin space, the decimal separator is a comma,
    and a whole amount drops the trailing zeros (``52 500``, not ``52 500,00``).
    ``None`` becomes an em dash so tables stay readable.
    """
    if value is None:
        return "—"
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return "—"

    formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    formatted = formatted.removesuffix(",00")
    return f"{prefix}{formatted} ₽"
