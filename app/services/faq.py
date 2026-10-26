"""FAQ content and search.

The questions are editorial rather than user-generated, so they live in code
instead of a table: no migration, no admin screen, and the text is versioned
with the app.  Search is a simple case-insensitive substring match over the
question and answer, which is enough for a list this size.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer: str
    category: str

    @property
    def anchor(self) -> str:
        """Stable id for deep-linking a single answer."""
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in self.question)
        while "--" in safe:
            safe = safe.replace("--", "-")
        return "faq-" + safe.strip("-")[:60]


CATEGORIES: tuple[str, ...] = ("Общее", "Сроки", "Оплата", "Процесс", "Поддержка")

ITEMS: tuple[FaqItem, ...] = (
    FaqItem(
        question="Сколько стоит разработка сайта?",
        answer=(
            "Стоимость зависит от объёма. Одностраничный сайт начинается от "
            "500 ₽, многостраничный — от 5 000 ₽. Точную смету фиксируем после "
            "обсуждения задачи: в калькуляторе можно получить ориентир за минуту."
        ),
        category="Оплата",
    ),
    FaqItem(
        question="Сколько времени занимает проект?",
        answer=(
            "Типовой одностраничный сайт — от 2 дней, многостраничный — от "
            "7 дней, Telegram-бот — от 2 дней, автоматизация скриптов — от 1 дня. "
            "Сроки фиксируем на старте и держим вас в курсе на каждом этапе."
        ),
        category="Сроки",
    ),
    FaqItem(
        question="Как проходит работа над проектом?",
        answer=(
            "Начинаем с обсуждения задачи в чате по заказу. Затем фиксируем "
            "состав работ и стоимость, показываем промежуточные результаты и "
            "сдаём проект с доступами. Все этапы видны в личном кабинете."
        ),
        category="Процесс",
    ),
    FaqItem(
        question="Нужна ли предоплата?",
        answer=(
            "Для небольших проектов работаем по факту сдачи. Для крупных "
            "разбиваем оплату на этапы: часть на старте, часть по готовности. "
            "Условия всегда согласуем заранее."
        ),
        category="Оплата",
    ),
    FaqItem(
        question="Что входит в поддержку после запуска?",
        answer=(
            "Мы не исчезаем после сдачи: следим за работой проекта, исправляем "
            "ошибки и помогаем с доработками. Первый месяц поддержки по мелким "
            "правкам входит в стоимость."
        ),
        category="Поддержка",
    ),
    FaqItem(
        question="Работаете ли вы с готовыми сайтами?",
        answer=(
            "Да. Можем доработать существующий сайт, ускорить загрузку, "
            "подключить бота или автоматизацию к текущему проекту — "
            "даже если он сделан не нами."
        ),
        category="Общее",
    ),
    FaqItem(
        question="Кому принадлежат исходники и доступы?",
        answer=(
            "Вам. После сдачи передаём доступы к хостингу, домену и репозиторию. "
            "Вы не привязаны к нам и можете развивать проект с любой командой."
        ),
        category="Процесс",
    ),
    FaqItem(
        question="Можно ли доработать проект после сдачи?",
        answer=(
            "Конечно. Небольшие правки делаем в рамках поддержки, крупные "
            "доработки оформляем отдельной задачей с понятной оценкой по срокам "
            "и стоимости."
        ),
        category="Поддержка",
    ),
)


def all_items() -> list[FaqItem]:
    return list(ITEMS)


def search(query: str) -> list[FaqItem]:
    """Case-insensitive substring search over question and answer."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(ITEMS)
    return [
        item
        for item in ITEMS
        if needle in item.question.lower() or needle in item.answer.lower()
    ]


def grouped() -> dict[str, list[FaqItem]]:
    """Items bucketed by category, in the declared category order."""
    buckets: dict[str, list[FaqItem]] = {name: [] for name in CATEGORIES}
    for item in ITEMS:
        buckets.setdefault(item.category, []).append(item)
    return {name: items for name, items in buckets.items() if items}
