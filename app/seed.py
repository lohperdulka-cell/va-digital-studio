"""Idempotent development seed data.

Run with ``python -m app.seed`` (or ``python -m app.seed --reset`` to drop the
service/news rows first).  Safe to run repeatedly: rows are matched by slug.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.logging_config import get_logger, setup_logging
from app.models import Case, News, NewsLike, Review, Service, User
from app.models.enums import ServiceCategory

logger = get_logger(__name__)

SERVICES: list[dict] = [
    {
        "slug": "landing-page",
        "title": "Лендинг под ключ",
        "short_description": (
            "Одностраничный сайт с заявками: структура, дизайн, вёрстка и запуск."
        ),
        "description": (
            "<p>Собираем страницу, которая приводит клиентов:</p>"
            "<ul>"
            "<li>прототип и структура под вашу услугу</li>"
            "<li>адаптивный дизайн под мобильные</li>"
            "<li>форма заявки и уведомления в Telegram</li>"
            "<li>подключение домена и базовой аналитики</li>"
            "</ul>"
            "<p>Срок — от 3 дней. Готовый сайт передаём с доступами.</p>"
        ),
        "category": ServiceCategory.SITES,
        "tags": ["лендинг", "адаптив", "форма заявок"],
        "price_from": Decimal("5000.00"),
        "duration_days": 3,
        "icon": "🌐",
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "slug": "telegram-bot-orders",
        "title": "Telegram-бот для заявок",
        "short_description": (
            "Бот принимает заявки, отвечает клиентам и присылает уведомления вам."
        ),
        "description": (
            "<p>Автоматизируем приём заявок в Telegram:</p>"
            "<ul>"
            "<li>пошаговый опрос и приём заявки</li>"
            "<li>уведомление менеджеру о новом обращении</li>"
            "<li>запись заявок в Google Sheets или базу</li>"
            "<li>простая админ-панель со статистикой</li>"
            "</ul>"
            "<p>Срок — от 2 дней. Хостинг бота подберём вместе.</p>"
        ),
        "category": ServiceCategory.BOTS,
        "tags": ["aiogram", "Telegram API", "заявки"],
        "price_from": Decimal("3500.00"),
        "duration_days": 2,
        "icon": "🤖",
        "is_featured": True,
        "sort_order": 2,
    },
    {
        "slug": "automation-script",
        "title": "Автоматизация рутины",
        "short_description": (
            "Скрипт, который убирает повторяющуюся работу: отчёты, выгрузки, рассылки."
        ),
        "description": (
            "<p>Берём одну рутинную задачу и убираем её полностью:</p>"
            "<ul>"
            "<li>автоматические отчёты по расписанию</li>"
            "<li>синхронизация таблиц и CRM</li>"
            "<li>сбор данных с сайтов и выгрузка в удобном виде</li>"
            "<li>уведомления в Telegram при важных событиях</li>"
            "</ul>"
            "<p>Срок — от 1 дня. Работает без вашего участия.</p>"
        ),
        "category": ServiceCategory.AUTOMATION,
        "tags": ["Python", "API", "отчёты"],
        "price_from": Decimal("1500.00"),
        "duration_days": 1,
        "icon": "⚙️",
        "is_featured": True,
        "sort_order": 3,
    },
    {
        "slug": "banner-design",
        "title": "Дизайн баннера и карточки",
        "short_description": (
            "Баннеры, обложки и карточки товаров для соцсетей и маркетплейсов."
        ),
        "description": (
            "<p>Делаем аккуратную графику под вашу задачу:</p>"
            "<ul>"
            "<li>баннеры и обложки для соцсетей</li>"
            "<li>карточки товаров для маркетплейсов</li>"
            "<li>единый стиль и шрифты</li>"
            "<li>исходники в удобном формате</li>"
            "</ul>"
            "<p>Срок — от 1 дня. Правки входят в стоимость.</p>"
        ),
        "category": ServiceCategory.DESIGN,
        "tags": ["графика", "соцсети", "маркетплейсы"],
        "price_from": Decimal("500.00"),
        "duration_days": 1,
        "icon": "🎨",
        "is_featured": False,
        "sort_order": 4,
    },
]

NEWS: list[dict] = [
    {
        "slug": "landing-for-repair-studio",
        "title": "Запустили лендинг для студии ремонта",
        "preview": (
            "Сделали одностраничный сайт с расчётом стоимости и заявками, "
            "которые сразу приходят в Telegram."
        ),
        "body": (
            "<p>К нам обратилась студия ремонта квартир. Заявки принимали "
            "в мессенджерах, часть обращений терялась.</p>"
            "<h3>Что сделали</h3>"
            "<ul>"
            "<li>продумали структуру: услуги, цены, примеры работ</li>"
            "<li>собрали адаптивный лендинг под телефоны</li>"
            "<li>добавили форму заявки с уведомлением в Telegram</li>"
            "<li>подключили домен и базовую аналитику</li>"
            "</ul>"
            "<h3>Результат</h3>"
            "<p>Заявки больше не теряются: каждая сразу приходит менеджеру "
            "в Telegram с контактами клиента.</p>"
        ),
        "cover_emoji": "🌐",
    },
    {
        "slug": "delivery-bot-case",
        "title": "Бот принимает заявки для службы доставки",
        "preview": (
            "Сократили время оформления заказа с 10 до 2 минут и убрали "
            "ручной ввод адресов."
        ),
        "body": (
            "<p>Клиент — небольшая служба доставки. Диспетчер вручную "
            "переносил заявки из переписки в таблицу.</p>"
            "<h3>Что сделали</h3>"
            "<ul>"
            "<li>бот задаёт клиенту несколько вопросов и принимает заказ</li>"
            "<li>заявка автоматически попадает в Google Sheets</li>"
            "<li>диспетчер получает уведомление с адресом и телефоном</li>"
            "</ul>"
            "<h3>Результат</h3>"
            "<p>Оформление заказа занимает около двух минут, "
            "ошибки в адресах практически исчезли.</p>"
        ),
        "cover_emoji": "📦",
    },
    {
        "slug": "automated-reports-shop",
        "title": "Автоматизировали отчётность интернет-магазина",
        "preview": (
            "Владелец получает сводку продаж каждое утро вместо ручного "
            "сбора данных из трёх таблиц."
        ),
        "body": (
            "<p>Каждый день уходил час на сбор продаж из нескольких "
            "источников и сведение их в одну таблицу.</p>"
            "<h3>Что сделали</h3>"
            "<ul>"
            "<li>написали скрипт, который собирает данные автоматически</li>"
            "<li>настроили отправку сводки в Telegram каждое утро</li>"
            "<li>добавили контроль ошибок и уведомления о сбоях</li>"
            "</ul>"
            "<h3>Результат</h3>"
            "<p>Час ручной работы в день превратился в готовую сводку, "
            "которая приходит сама.</p>"
        ),
        "cover_emoji": "📊",
    },
    {
        "slug": "marketplace-cards",
        "title": "Собрали карточки товаров для маркетплейса",
        "preview": (
            "Оформили 40 карточек в едином стиле — продажи выросли "
            "за счёт понятных изображений."
        ),
        "body": (
            "<p>Товары на маркетплейсе выглядели разрозненно: разные "
            "шрифты, цвета и размеры изображений.</p>"
            "<h3>Что сделали</h3>"
            "<ul>"
            "<li>разработали единый стиль карточек</li>"
            "<li>подготовили 40 изображений с ключевыми характеристиками</li>"
            "<li>оформили обложки и инфографику</li>"
            "</ul>"
            "<h3>Результат</h3>"
            "<p>Витрина выглядит аккуратно, а покупателю проще "
            "сравнивать товары.</p>"
        ),
        "cover_emoji": "🎨",
    },
]

CASES: list[dict] = [
    {
        "slug": "repair-studio-landing",
        "title": "Лендинг для студии ремонта",
        "client": "Студия ремонта квартир",
        "summary": (
            "Одностраничный сайт с расчётом стоимости и заявками, "
            "которые мгновенно приходят в Telegram."
        ),
        "body": (
            "<p>Заявки принимали в мессенджерах, часть обращений терялась. "
            "Собрали лендинг с понятной структурой и автоматической доставкой "
            "заявок менеджеру.</p>"
            "<ul><li>прототип и структура под услугу</li>"
            "<li>адаптивный дизайн</li>"
            "<li>форма заявки с уведомлением в Telegram</li></ul>"
        ),
        "result_metric": "Заявки не теряются",
        "cover_emoji": "🌐",
        "tags": ["лендинг", "адаптив", "Telegram"],
        "service_slug": "landing-page",
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "slug": "delivery-orders-bot",
        "title": "Бот для службы доставки",
        "client": "Служба доставки",
        "summary": (
            "Оформление заказа сократилось с 10 до 2 минут, "
            "ручной ввод адресов убран."
        ),
        "body": (
            "<p>Диспетчер вручную переносил заявки из переписки в таблицу. "
            "Бот задаёт вопросы, принимает заказ и передаёт его диспетчеру.</p>"
            "<ul><li>пошаговый опрос клиента</li>"
            "<li>запись заявки в Google Sheets</li>"
            "<li>уведомление с адресом и телефоном</li></ul>"
        ),
        "result_metric": "Оформление ~2 мин",
        "cover_emoji": "📦",
        "tags": ["Telegram-бот", "заявки", "Google Sheets"],
        "service_slug": "telegram-bot-orders",
        "is_featured": True,
        "sort_order": 2,
    },
    {
        "slug": "shop-reports-automation",
        "title": "Автоотчётность интернет-магазина",
        "client": "Интернет-магазин",
        "summary": (
            "Владелец получает сводку продаж каждое утро вместо ручного "
            "сбора данных из трёх таблиц."
        ),
        "body": (
            "<p>Ежедневно уходил час на сведение продаж из нескольких "
            "источников. Автоматизировали сбор и отправку сводки.</p>"
            "<ul><li>скрипт собирает данные автоматически</li>"
            "<li>сводка приходит в Telegram каждое утро</li>"
            "<li>контроль ошибок и уведомления о сбоях</li></ul>"
        ),
        "result_metric": "−1 час рутины в день",
        "cover_emoji": "📊",
        "tags": ["Python", "отчёты", "автоматизация"],
        "service_slug": "automation-script",
        "is_featured": True,
        "sort_order": 3,
    },
]

REVIEWS: list[dict] = [
    {
        "author_name": "Алексей М.",
        "author_role": "Студия ремонта квартир",
        "rating": 5,
        "body": (
            "Сделали лендинг быстро и аккуратно. Заявки теперь приходят "
            "в Telegram, ничего не теряется. Отдельно порадовало, что "
            "объясняли каждый шаг."
        ),
        "is_approved": True,
    },
    {
        "author_name": "Марина К.",
        "author_role": "Служба доставки",
        "rating": 5,
        "body": (
            "Бот для заявок окупился за первую неделю. Диспетчер больше "
            "не переносит заказы вручную, а мы видим статистику в одном месте."
        ),
        "is_approved": True,
    },
    {
        "author_name": "Дмитрий В.",
        "author_role": "Интернет-магазин",
        "rating": 4,
        "body": (
            "Автоматизация отчётности работает стабильно уже несколько "
            "месяцев. Один раз потребовалась доработка — отреагировали "
            "в тот же день."
        ),
        "is_approved": True,
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


def seed_cases(db: Session) -> tuple[int, int]:
    created = updated = 0
    for payload in CASES:
        item = db.scalar(select(Case).where(Case.slug == payload["slug"]))
        if item is None:
            db.add(Case(**payload))
            created += 1
        else:
            for field, value in payload.items():
                setattr(item, field, value)
            updated += 1
    db.commit()
    return created, updated


def seed_reviews(db: Session) -> int:
    """Add sample reviews once, matched by author so a restart does not duplicate."""
    created = 0
    for payload in REVIEWS:
        exists = db.scalar(
            select(Review).where(Review.author_name == payload["author_name"])
        )
        if exists is None:
            db.add(Review(**payload))
            created += 1
    db.commit()
    return created


def promote_admins(db: Session) -> int:
    """Sync ``is_admin`` with ``ADMIN_EMAILS``; fall back to an owner account.

    ``ADMIN_EMAILS`` is authoritative: an address on the list is an admin, one
    that is not is demoted.  When the list is empty the oldest account owns the
    dashboard instead, because a card-free host has no Shell to run
    ``python -m app.cli make_admin`` in and the dashboard would otherwise be
    unreachable for everyone.
    """
    wanted = set(settings.admin_email_list)

    if not wanted:
        return _promote_owner_account(db)

    changed = 0
    for user in db.scalars(select(User)):
        should_be_admin = user.email in wanted
        if user.is_admin != should_be_admin:
            user.is_admin = should_be_admin
            changed += 1
    db.commit()
    return changed


def _promote_owner_account(db: Session) -> int:
    """Make the oldest account the owner when no ``ADMIN_EMAILS`` is set.

    Nothing happens once an administrator exists, so a later registration can
    never take the flag away from the owner.
    """
    has_admin = db.scalar(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )
    if has_admin:
        return 0

    owner = db.scalar(select(User).order_by(User.id).limit(1))
    if owner is None:
        return 0

    owner.is_admin = True
    db.commit()
    logger.info("No ADMIN_EMAILS set: promoted the owner account (%s)", owner.email)
    return 1


def reset_content(db: Session) -> None:
    """Remove seeded content (likes first, because of the FK)."""
    db.execute(delete(NewsLike))
    db.execute(delete(News))
    db.execute(delete(Service))
    db.execute(delete(Review))
    db.execute(delete(Case))
    db.commit()
    logger.warning("Seed content removed (services, news, cases, reviews, likes)")


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
        cases_created, cases_updated = seed_cases(db)
        reviews_created = seed_reviews(db)
        admins = promote_admins(db)

        service_total = len(list(db.scalars(select(Service))))
        news_total = len(list(db.scalars(select(News))))

    print("VA Digital Studio — сидинг завершён")
    print(f"  услуги:  +{services_created} новых, ~{services_updated} обновлено (всего {service_total})")
    print(f"  новости: +{news_created} новых, ~{news_updated} обновлено (всего {news_total})")
    print(f"  кейсы:   +{cases_created} новых, ~{cases_updated} обновлено")
    print(f"  отзывы:  +{reviews_created} новых")
    print(f"  админов назначено: {admins}")
    if not settings.admin_email_list:
        print(
            "  ⚠ ADMIN_EMAILS не задан — назначьте админа через "
            "`python -m app.cli make_admin <email>` после первого входа"
        )
    else:
        print(f"  ADMIN_EMAILS: {', '.join(settings.admin_email_list)}")


def bootstrap() -> None:
    """Startup hook: fill empty content tables, then sync admin rights.

    Each table is seeded only when it is empty, so a redeploy never overwrites
    edits made through the dashboard.  Admin promotion runs on every start
    because it is idempotent, and it lets a changed ADMIN_EMAILS take effect
    without the operator logging out and back in.
    """
    setup_logging()
    # start.sh runs alembic first, so this is normally a no-op; it only spares
    # a container that skipped migrations from crashing on a missing table.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        service_total = db.scalar(select(func.count()).select_from(Service)) or 0
        if service_total == 0:
            services_created, _ = seed_services(db)
            news_created, _ = seed_news(db)
            print(
                "[bootstrap] каталог был пуст — заполнен: "
                f"услуги +{services_created}, новости +{news_created}"
            )
            logger.info(
                "Bootstrap seeded an empty catalogue: services=%s news=%s",
                services_created,
                news_created,
            )
        else:
            print(f"[bootstrap] каталог уже заполнен ({service_total} услуг) — пропускаю")

        # Cases and reviews are seeded independently of the catalogue: an
        # existing deployment gains them on the next redeploy without touching
        # the services/news it already has.
        case_total = db.scalar(select(func.count()).select_from(Case)) or 0
        if case_total == 0:
            cases_created, _ = seed_cases(db)
            print(f"[bootstrap] кейсы добавлены: +{cases_created}")

        review_total = db.scalar(select(func.count()).select_from(Review)) or 0
        if review_total == 0:
            reviews_created = seed_reviews(db)
            print(f"[bootstrap] отзывы добавлены: +{reviews_created}")

        promoted = promote_admins(db)
        if promoted:
            print(f"[bootstrap] права администратора обновлены: {promoted}")
            logger.info("Bootstrap promoted %s admin account(s)", promoted)


def main() -> int:
    if "--bootstrap" in sys.argv:
        bootstrap()
        return 0
    run(reset="--reset" in sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
