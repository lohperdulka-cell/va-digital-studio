"""Idempotent development seed data.

Run with ``python -m app.seed`` (or ``python -m app.seed --reset`` to drop the
service/news rows first).  Safe to run repeatedly: rows are matched by slug.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.logging_config import get_logger, setup_logging
from app.models import News, NewsLike, Service, User
from app.models.enums import ServiceCategory

logger = get_logger(__name__)

SERVICES: list[dict] = [
    {
        "slug": "website-development",
        "title": "Разработка сайтов",
        "short_description": (
            "Корпоративные сайты, лендинги и интернет-магазины: "
            "от прототипа до продакшена."
        ),
        "description": (
            "<p>Проектируем и собираем сайты, которые продают:</p>"
            "<ul>"
            "<li>аналитика ниши и конкурентов, прототип и структура</li>"
            "<li>дизайн в Figma с адаптивом под мобильные</li>"
            "<li>вёрстка и разработка на современном стеке</li>"
            "<li>подключение аналитики, CRM и форм заявок</li>"
            "<li>SEO-база: мета-теги, микроразметка, скорость</li>"
            "</ul>"
            "<p>После запуска передаём доступы и инструкции по управлению.</p>"
        ),
        "category": ServiceCategory.SITES,
        "tags": ["FastAPI", "React", "адаптив", "SEO"],
        "price_from": Decimal("45000.00"),
        "duration_days": 21,
        "icon": "🌐",
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "slug": "telegram-bots",
        "title": "Telegram-боты",
        "short_description": (
            "Боты для приёма заявок, оплаты, поддержки и интеграций с вашими системами."
        ),
        "description": (
            "<p>Автоматизируем общение с клиентами в Telegram:</p>"
            "<ul>"
            "<li>приём заявок и запись на услугу</li>"
            "<li>приём платежей и отправка чеков</li>"
            "<li>интеграция с CRM, Google Sheets и 1С</li>"
            "<li>рассылки и сегментация аудитории</li>"
            "<li>админ-панель со статистикой</li>"
            "</ul>"
        ),
        "category": ServiceCategory.BOTS,
        "tags": ["aiogram", "Telegram API", "платежи", "CRM"],
        "price_from": Decimal("30000.00"),
        "duration_days": 14,
        "icon": "🤖",
        "is_featured": True,
        "sort_order": 2,
    },
    {
        "slug": "business-automation",
        "title": "Автоматизация процессов",
        "short_description": (
            "Убираем рутину: отчёты, выгрузки, синхронизация данных между сервисами."
        ),
        "description": (
            "<p>Находим узкие места и автоматизируем их:</p>"
            "<ul>"
            "<li>автоматические отчёты и дашборды</li>"
            "<li>синхронизация данных между CRM, таблицами и складом</li>"
            "<li>парсинг и обогащение данных</li>"
            "<li>уведомления в Telegram при важных событиях</li>"
            "<li>резервное копирование и контроль ошибок</li>"
            "</ul>"
        ),
        "category": ServiceCategory.AUTOMATION,
        "tags": ["Python", "API", "ETL", "отчёты"],
        "price_from": Decimal("25000.00"),
        "duration_days": 10,
        "icon": "⚙️",
        "is_featured": True,
        "sort_order": 3,
    },
    {
        "slug": "ui-ux-design",
        "title": "Дизайн интерфейсов",
        "short_description": (
            "UI/UX для сайтов и приложений: исследование, прототип, дизайн-система."
        ),
        "description": (
            "<p>Делаем интерфейсы понятными и приятными:</p>"
            "<ul>"
            "<li>исследование аудитории и анализ конкурентов</li>"
            "<li>информационная архитектура и прототипы</li>"
            "<li>визуальный дизайн и UI-kit</li>"
            "<li>дизайн-система для командной работы</li>"
            "<li>подготовка макетов к вёрстке</li>"
            "</ul>"
        ),
        "category": ServiceCategory.DESIGN,
        "tags": ["Figma", "UI-kit", "прототип", "брендинг"],
        "price_from": Decimal("35000.00"),
        "duration_days": 18,
        "icon": "🎨",
        "is_featured": False,
        "sort_order": 4,
    },
    {
        "slug": "technical-support",
        "title": "Техподдержка и развитие",
        "short_description": (
            "Следим за стабильностью, обновляем зависимости, дорабатываем по запросу."
        ),
        "description": (
            "<p>Берём на себя техническую эксплуатацию:</p>"
            "<ul>"
            "<li>мониторинг доступности и ошибок</li>"
            "<li>обновление зависимостей и безопасность</li>"
            "<li>резервные копии и восстановление</li>"
            "<li>доработки и мелкие задачи по часам</li>"
            "<li>консультации по развитию продукта</li>"
            "</ul>"
        ),
        "category": ServiceCategory.AUTOMATION,
        "tags": ["Docker", "мониторинг", "бэкапы", "SLA"],
        "price_from": Decimal("15000.00"),
        "duration_days": 7,
        "icon": "🛡️",
        "is_featured": False,
        "sort_order": 5,
    },
    {
        "slug": "seo-promotion",
        "title": "SEO-продвижение",
        "short_description": (
            "Технический аудит, семантика и контент-стратегия для роста в поиске."
        ),
        "description": (
            "<p>Работаем над видимостью в поисковых системах:</p>"
            "<ul>"
            "<li>технический аудит сайта и исправление ошибок</li>"
            "<li>сбор семантики и кластеризация запросов</li>"
            "<li>оптимизация мета-тегов и структуры</li>"
            "<li>контент-план и рекомендации по текстам</li>"
            "<li>ежемесячный отчёт по позициям и трафику</li>"
            "</ul>"
        ),
        "category": ServiceCategory.SITES,
        "tags": ["SEO", "аналитика", "контент", "аудит"],
        "price_from": Decimal("20000.00"),
        "duration_days": 30,
        "icon": "📈",
        "is_featured": False,
        "sort_order": 6,
    },
]

NEWS: list[dict] = [
    {
        "slug": "studio-launch",
        "title": "VA Digital Studio открывает новый сезон проектов",
        "preview": (
            "Мы обновили сайт, добавили личный кабинет с чатом по заказам "
            "и стали быстрее отвечать на заявки."
        ),
        "body": (
            "<p>За последний год мы выросли: теперь в команде есть отдельный "
            "направления по разработке, дизайну и автоматизации.</p>"
            "<p>Что нового:</p>"
            "<ul>"
            "<li>личный кабинет с историей заказов и балансом</li>"
            "<li>чат по каждому проекту с менеджером</li>"
            "<li>прозрачные статусы: от черновика до завершения</li>"
            "</ul>"
            "<p>Спасибо, что были с нами — впереди много интересного.</p>"
        ),
        "cover_emoji": "🚀",
    },
    {
        "slug": "telegram-bot-case-study",
        "title": "Кейс: Telegram-бот для службы доставки",
        "preview": (
            "Сократили время обработки заказа с 15 до 2 минут и убрали "
            "ручной ввод адресов из процесса."
        ),
        "body": (
            "<p>Клиент — служба доставки с 40 курьерами. Заявки принимали "
            "по телефону, диспетчер вручную заносил их в таблицу.</p>"
            "<h3>Что сделали</h3>"
            "<ul>"
            "<li>бот принимает заказ и проверяет адрес по карте</li>"
            "<li>заявка сразу попадает в CRM и распределяется по курьерам</li>"
            "<li>клиент видит статус доставки в боте</li>"
            "</ul>"
            "<h3>Результат</h3>"
            "<p>Время обработки заказа сократилось с 15 до 2 минут, "
            "количество ошибок в адресах упало почти до нуля.</p>"
        ),
        "cover_emoji": "📦",
    },
    {
        "slug": "why-automation-pays-off",
        "title": "Как посчитать выгоду от автоматизации",
        "preview": (
            "Простая формула, которая помогает понять, окупится ли автоматизация "
            "рутинной задачи в вашей компании."
        ),
        "body": (
            "<p>Автоматизацию часто считают «дорогой игрушкой». На самом деле "
            "достаточно двух цифр: сколько часов в месяц уходит на рутину и "
            "сколько стоит час сотрудника.</p>"
            "<blockquote>Экономия = часы в месяц × стоимость часа × 12</blockquote>"
            "<p>Если задача занимает у двух человек по 10 часов в месяц, "
            "при стоимости часа 800 ₽ годовая экономия — около 192 000 ₽.</p>"
            "<p>Сравните с бюджетом разработки — обычно решение окупается "
            "за первые 3–6 месяцев.</p>"
        ),
        "cover_emoji": "📊",
    },
]


def seed_services(db: Session) -> tuple[int, int]:
    created = updated = 0
    for payload in SERVICES:
        service = db.scalar(select(Service).where(Service.slug == payload["slug"]))
        if service is None:
            db.add(Service(**payload))
            created += 1
        else:
            for field, value in payload.items():
                setattr(service, field, value)
            updated += 1
    db.commit()
    return created, updated


def seed_news(db: Session) -> tuple[int, int]:
    created = updated = 0
    for payload in NEWS:
        item = db.scalar(select(News).where(News.slug == payload["slug"]))
        if item is None:
            db.add(News(**payload))
            created += 1
        else:
            for field, value in payload.items():
                setattr(item, field, value)
            updated += 1
    db.commit()
    return created, updated


def promote_admins(db: Session) -> int:
    """Promote any existing user whose e-mail is in ADMIN_EMAILS."""
    wanted = set(settings.admin_email_list)
    if not wanted:
        return 0
    changed = 0
    for user in db.scalars(select(User)):
        should_be_admin = user.email in wanted
        if user.is_admin != should_be_admin:
            user.is_admin = should_be_admin
            changed += 1
    db.commit()
    return changed


def reset_content(db: Session) -> None:
    """Remove seeded content (likes first, because of the FK)."""
    db.execute(delete(NewsLike))
    db.execute(delete(News))
    db.execute(delete(Service))
    db.commit()
    logger.warning("Seed content removed (services, news, likes)")


def run(*, reset: bool = False) -> None:
    setup_logging()
    # Alembic is the source of truth for schema; create_all here only spares a
    # fresh dev checkout an extra step and is a no-op when tables exist.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if reset:
            reset_content(db)

        services_created, services_updated = seed_services(db)
        news_created, news_updated = seed_news(db)
        admins = promote_admins(db)

        service_total = len(list(db.scalars(select(Service))))
        news_total = len(list(db.scalars(select(News))))

    print("VA Digital Studio — сидинг завершён")
    print(f"  услуги:  +{services_created} новых, ~{services_updated} обновлено (всего {service_total})")
    print(f"  новости: +{news_created} новых, ~{news_updated} обновлено (всего {news_total})")
    print(f"  админов назначено: {admins}")
    if not settings.admin_email_list:
        print(
            "  ⚠ ADMIN_EMAILS не задан — назначьте админа через "
            "`python -m app.cli make_admin <email>` после первого входа"
        )
    else:
        print(f"  ADMIN_EMAILS: {', '.join(settings.admin_email_list)}")


def main() -> int:
    run(reset="--reset" in sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
