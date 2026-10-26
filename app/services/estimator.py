"""Cost calculator: turns a few answers into a price range and a timeline.

The numbers are deliberately simple and fully data-driven from the answers —
no hidden table to keep in sync.  Each option contributes a multiplier to the
base price of the chosen service type and an additive number of days; the
result is presented as a range so the client never reads it as a firm quote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.i18n import t as _t

# Base price and lead time per project type.  Prices are the studio's entry
# points; the catalogue's `price_from` mirrors them.
BASE_PRICE: dict[str, Decimal] = {
    "landing": Decimal("500"),
    "corporate": Decimal("5000"),
    "bot": Decimal("3500"),
    "automation": Decimal("1500"),
}

BASE_DAYS: dict[str, int] = {
    "landing": 2,
    "corporate": 7,
    "bot": 2,
    "automation": 1,
}

PROJECT_LABELS: dict[str, str] = {
    "landing": "Одностраничный сайт",
    "corporate": "Многостраничный сайт",
    "bot": "Telegram-бот",
    "automation": "Автоматизация",
}

# Scope answers: multiplier on the base price and extra days.
SCOPE_FACTORS: dict[str, tuple[Decimal, int]] = {
    "basic": (Decimal("1.0"), 0),
    "standard": (Decimal("1.4"), 2),
    "extended": (Decimal("2.0"), 5),
}

SCOPE_LABELS: dict[str, str] = {
    "basic": "Базовый объём",
    "standard": "Расширенный",
    "extended": "Максимальный",
}

# Deadline answers: a rush surcharge and a shorter (or longer) timeline.
DEADLINE_FACTORS: dict[str, tuple[Decimal, float]] = {
    "relaxed": (Decimal("1.0"), 1.0),
    "normal": (Decimal("1.1"), 0.75),
    "urgent": (Decimal("1.3"), 0.5),
}

DEADLINE_LABELS: dict[str, str] = {
    "relaxed": "Спокойно, есть время",
    "normal": "Стандартные сроки",
    "urgent": "Срочно",
}

# One-time add-ons: a flat extra charge and days.
ADDONS: dict[str, tuple[Decimal, int]] = {
    "content": (Decimal("2000"), 2),
    "integrations": (Decimal("2500"), 2),
    "support": (Decimal("1500"), 0),
}

ADDON_LABELS: dict[str, str] = {
    "content": "Тексты и наполнение",
    "integrations": "Интеграции (CRM, оплата)",
    "support": "Поддержка 3 месяца",
}

# The displayed range: the exact estimate sits between these two bounds.
RANGE_LOW = Decimal("0.9")
RANGE_HIGH = Decimal("1.15")


@dataclass(frozen=True)
class Estimate:
    """A calculator result, ready for rendering."""

    price_low: Decimal
    price_high: Decimal
    days: int
    breakdown: list[str] = field(default_factory=list)


def project_types() -> list[tuple[str, str]]:
    return [(_key, _t(_label)) for _key, _label in PROJECT_LABELS.items()]


def scopes() -> list[tuple[str, str]]:
    return [(_key, _t(_label)) for _key, _label in SCOPE_LABELS.items()]


def deadlines() -> list[tuple[str, str]]:
    return [(_key, _t(_label)) for _key, _label in DEADLINE_LABELS.items()]


def addon_options() -> list[tuple[str, str]]:
    return [(_key, _t(_label)) for _key, _label in ADDON_LABELS.items()]


def estimate(
    *,
    project_type: str,
    scope: str = "standard",
    deadline: str = "normal",
    addons: list[str] | None = None,
) -> Estimate:
    """Compute a price range and timeline from the submitted answers.

    Unknown keys fall back to the safest default rather than raising: the form
    is the only caller and a stale bookmark should still produce something
    sensible.
    """
    base = BASE_PRICE.get(project_type, BASE_PRICE["landing"])
    base_days = BASE_DAYS.get(project_type, BASE_DAYS["landing"])
    breakdown = [f"{_t(PROJECT_LABELS.get(project_type, 'Проект'))}: {base:.0f} ₽"]

    scope_factor, scope_days = SCOPE_FACTORS.get(scope, SCOPE_FACTORS["standard"])
    deadline_factor, deadline_days = DEADLINE_FACTORS.get(
        deadline, DEADLINE_FACTORS["normal"]
    )

    price = base * scope_factor
    if scope_factor != Decimal("1.0"):
        breakdown.append(
            f"{_t(SCOPE_LABELS.get(scope, scope))}: ×{scope_factor}"
        )

    price *= deadline_factor
    if deadline_factor != Decimal("1.0"):
        breakdown.append(
            f"{_t(DEADLINE_LABELS.get(deadline, deadline))}: +"
            f"{int((deadline_factor - 1) * 100)}%"
        )

    days = base_days + scope_days
    for key in addons or []:
        if key not in ADDONS:
            continue
        extra_price, extra_days = ADDONS[key]
        price += extra_price
        days += extra_days
        breakdown.append(f"{_t(ADDON_LABELS[key])}: +{extra_price:.0f} ₽")

    days = max(1, round(days * deadline_days))
    price_low = (price * RANGE_LOW).quantize(Decimal("1"))
    price_high = (price * RANGE_HIGH).quantize(Decimal("1"))
    return Estimate(
        price_low=price_low,
        price_high=price_high,
        days=days,
        breakdown=breakdown,
    )
