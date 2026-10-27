"""Bilingual UI: Russian (default) and English.

The catalogue maps a Russian source string to its English text, so templates
read ``{{ t("Услуги студии") }}``.  Keys are the Russian text itself rather
than invented identifiers: the reviewer of a translation sees the sentence it
replaces, and a missing entry degrades to Russian instead of showing a key.

Russian is the default, and ``t`` returns the source unchanged for it, so the
existing Russian output (and the tests asserting it) is unaffected.

Only the interface is translated.  Content edited in the dashboard — services,
news, cases, reviews — is stored in one language and shown as entered.
"""

from __future__ import annotations

from contextvars import ContextVar

DEFAULT_LOCALE = "ru"
SUPPORTED_LOCALES = ("ru", "en")

#: Cookie holding the visitor's choice; read on every request.
LOCALE_COOKIE_NAME = "va_lang"

#: Query parameter that overrides the cookie for a single link.
LOCALE_QUERY_PARAM = "lang"

_current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)


def normalize_locale(value: str | None) -> str | None:
    """Return a supported locale code, or ``None`` when unusable.

    ``en-US`` and ``EN`` both collapse to ``en`` so a browser's Accept-Language
    header and a hand-typed ``?lang=`` behave the same way.
    """
    if not value:
        return None
    code = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in SUPPORTED_LOCALES else None


def get_locale() -> str:
    return _current_locale.get()


def set_locale(code: str | None) -> str:
    """Set the locale for the current request; returns what was applied."""
    resolved = normalize_locale(code) or DEFAULT_LOCALE
    _current_locale.set(resolved)
    return resolved


def is_english() -> bool:
    return get_locale() == "en"


def _normalize(text: str) -> str:
    """Collapse runs of whitespace into single spaces.

    Templates wrap long sentences across lines, so the literal text contains
    newlines and indentation while the catalogue stores a single-space form.
    Normalising both sides lets one entry match either layout.
    """
    return " ".join(text.split())


def t(text: str, **fmt: object) -> str:
    """Translate ``text`` into the active locale.

    ``fmt`` values are interpolated after lookup, so a translated string may
    reorder ``{name}`` placeholders freely.  A missing translation returns the
    Russian source: a Russian sentence is far better than a bare key.
    """
    translated = text
    if is_english():
        translated = TRANSLATIONS.get(_normalize(text), text)
    if fmt:
        try:
            return translated.format(**fmt)
        except (KeyError, IndexError):  # pragma: no cover - authoring mistake
            return translated
    return translated


def plural(count: int, one: str, few: str, many: str) -> str:
    """Russian pluralisation: 1 услуга / 2 услуги / 5 услуг."""
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def en_plural(count: int, one: str, many: str) -> str:
    """English pluralisation; Russian rules do not apply to English nouns."""
    return one if abs(int(count)) == 1 else many


def count_label(count: int, one_ru: str, few_ru: str, many_ru: str, one_en: str, many_en: str) -> str:
    """Pick the right noun form for the active locale.

    Keeps the two languages' plural rules out of the templates, which would
    otherwise need a locale test at every counter.
    """
    if is_english():
        return en_plural(count, one_en, many_en)
    return plural(count, one_ru, few_ru, many_ru)


def other_locale() -> str:
    """The locale the switcher should offer next."""
    return "en" if get_locale() == "ru" else "ru"


# --- Catalogue -------------------------------------------------------------

TRANSLATIONS: dict[str, str] = {
    # --- Navigation and shared chrome -------------------------------------
    "Главная": "Home",
    "Каталог": "Catalog",
    "Каталог услуг": "Services",
    "Портфолио": "Portfolio",
    "Новости": "News",
    "Калькулятор": "Calculator",
    "Калькулятор стоимости": "Cost calculator",
    "Отзывы": "Reviews",
    "О студии": "About",
    "Дашборд": "Dashboard",
    "Поддержка": "Support",
    "Служба поддержки": "Support",
    "Профиль": "Profile",
    "Мои заказы": "My orders",
    "Личный кабинет": "Account",
    "Войти": "Sign in",
    "Выйти": "Sign out",
    "Зарегистрироваться": "Create an account",
    "Основная навигация": "Main navigation",
    "Меню навигации": "Navigation menu",
    "Открыть меню": "Open menu",
    "Закрыть меню": "Close menu",
    "Закрыть": "Close",
    "Навигация": "Breadcrumb",
    "Перейти к содержимому": "Skip to content",
    "Постраничная навигация": "Pagination",
    "Язык": "Language",
    "Русский": "Russian",
    "Английский": "English",
    "Сменить язык": "Switch language",

    # --- Footer -----------------------------------------------------------
    "Услуги": "Services",
    "Разработка сайтов": "Web development",
    "Telegram-боты": "Telegram bots",
    "Автоматизация": "Automation",
    "Все услуги": "All services",
    "О нас": "About us",
    "Вопросы и ответы": "FAQ",
    "Контакты": "Contacts",
    "Политика конфиденциальности": "Privacy policy",
    "Все права защищены.": "All rights reserved.",
    "Создаём сайты, Telegram-ботов и автоматизацию, которые работают на бизнес. Полный цикл: аналитика, разработка, поддержка.": (
        "We build websites, Telegram bots and automation that work for your "
        "business. Full cycle: research, development, support."
    ),
    "Пн–Пт, 10:00–19:00 (МСК)": "Mon–Fri, 10:00–19:00 (MSK)",

    # --- Home page --------------------------------------------------------
    "VA Digital Studio — сайты, Telegram-боты, автоматизация": (
        "VA Digital Studio — websites, Telegram bots, automation"
    ),
    "VA Digital Studio — разработка сайтов, Telegram-ботов и автоматизация под ключ.": (
        "VA Digital Studio — turnkey websites, Telegram bots and automation."
    ),
    "⚡ Цифровые продукты под ключ": "⚡ Turnkey digital products",
    "Превращаем идеи в": "We turn ideas into",
    "работающие продукты": "products that work",
    "Проектируем и разрабатываем сайты, Telegram-ботов и автоматизацию, которая экономит часы вашей команды. Берём на себя всё: от аналитики до поддержки после запуска.": (
        "We design and build websites, Telegram bots and automation that save "
        "your team hours. We handle everything: from research to post-launch "
        "support."
    ),
    "Смотреть услуги": "Browse services",
    "Оставить заявку": "Send a request",
    "направлений услуг": "service areas",
    "проектов в работе и завершено": "projects in progress and completed",
    "дней средний срок запуска": "days average time to launch",
    "готово": "done",
    "за 14 дней": "in 14 days",
    "Наши услуги": "Our services",
    "Что мы делаем": "What we do",
    "Выберите направление — на странице услуги есть состав работ, сроки и стоимость.": (
        "Pick a service — each page lists the scope, timeline and price."
    ),
    "Подробнее": "Details",
    "Все услуги →": "All services →",
    "Каталог наполняется": "The catalog is filling up",
    "Скоро здесь появятся наши услуги. Оставьте заявку — расскажем подробнее.": (
        "Our services will appear here soon. Send a request and we will tell "
        "you more."
    ),
    "Погружаемся в задачу": "We dig into the task",
    "Начинаем с бизнес-цели, а не с шаблона. Решение подстраиваем под ваш процесс.": (
        "We start from the business goal, not a template, and shape the "
        "solution around your process."
    ),
    "Прозрачный процесс": "A transparent process",
    "Статусы, чат по проекту и фиксированная смета — вы всегда знаете, на каком этапе работа.": (
        "Statuses, a per-project chat and a fixed estimate — you always know "
        "where the work stands."
    ),
    "Быстрый запуск": "Fast launch",
    "Типовые проекты — от 7 дней. Никаких месяцев ожидания и потерянных договорённостей.": (
        "Typical projects take from 7 days. No months of waiting, no lost "
        "agreements."
    ),
    "Поддержка после": "Support afterwards",
    "Не исчезаем после сдачи: следим за работой, обновляем и развиваем продукт.": (
        "We do not disappear after delivery: we monitor, update and grow the "
        "product."
    ),
    "Что происходит в студии": "What is happening at the studio",
    "Все новости →": "All news →",
    "Кейсы с результатом": "Case studies with results",
    "Реальные проекты и то, что они дали клиентам.": (
        "Real projects and what they delivered for the clients."
    ),
    "Топ": "Top",
    "Смотреть кейс": "View case",
    "Все кейсы →": "All cases →",
    "Нам доверяют": "Clients trust us",
    "Все отзывы →": "All reviews →",
    "Оставить отзыв": "Leave a review",
    "Остались вопросы?": "Still have questions?",
    "Посмотрите ответы на частые вопросы или рассчитайте стоимость проекта за минуту — без звонков и ожидания.": (
        "Read the frequently asked questions or estimate your project in a "
        "minute — no calls, no waiting."
    ),
    "Частые вопросы": "FAQ",
    "Обсудим ваш проект?": "Shall we discuss your project?",
    "Оставьте заявку — вернёмся с уточняющими вопросами и предложением в течение одного рабочего дня.": (
        "Send a request and we will come back with questions and a proposal "
        "within one business day."
    ),

    # --- Catalog and service pages ----------------------------------------
    "Услуги студии": "Studio services",
    "Выберите направление или откройте карточку, чтобы увидеть состав работ и сроки.": (
        "Pick a direction or open a card to see the scope and timeline."
    ),
    "Все": "All",
    "Активные": "Active",
    "Завершённые": "Completed",
    "дн.": "d",
    "Ничего не найдено": "Nothing found",
    "В этой категории пока нет услуг.": "There are no services in this category yet.",
    "Каталог наполняется.": "The catalog is filling up.",
    "Показать все услуги": "Show all services",
    "Состав работ": "Scope of work",
    "Технологии и теги": "Technologies and tags",
    "Итоговая стоимость зависит от объёма задач и согласуется в чате.": (
        "The final price depends on the scope and is agreed in the chat."
    ),
    "Категория": "Category",
    "Срок": "Timeline",
    "Формат": "Format",
    "Обсудим в чате": "Agreed in the chat",
    "Заказать": "Order",
    "Задать вопрос": "Ask a question",
    "Создадим черновик заказа и откроем чат с менеджером": (
        "We will create a draft order and open a chat with a manager"
    ),
    "Как мы работаем": "How we work",
    "Обсуждаем задачу в чате по заказу": "We discuss the task in the order chat",
    "Фиксируем состав работ и стоимость": "We fix the scope and the price",
    "Разрабатываем и показываем промежуточные результаты": (
        "We develop and show intermediate results"
    ),
    "Сдаём проект и остаёмся на поддержке": "We deliver the project and stay for support",
    "Похожие услуги": "Similar services",

    # --- About ------------------------------------------------------------
    "О студии ·": "About ·",
    "Небольшая команда с": "A small team with",
    "большим фокусом": "a sharp focus",
    "VA Digital Studio — это разработка сайтов, ботов и автоматизация в одном месте. Мы не распыляемся: берём проекты, в которых можем довести результат до конца.": (
        "VA Digital Studio is web development, bots and automation in one place. "
        "We do not spread thin: we take projects we can see through to the end."
    ),
    "Понятные договорённости": "Clear agreements",
    "Смета, сроки и состав работ фиксируются до старта. Без «доплатите за мелочь».": (
        "The estimate, timeline and scope are fixed before we start. No "
        "\"pay extra for a small thing\"."
    ),
    "Прямая коммуникация": "Direct communication",
    "Чат по каждому проекту: видно статус, историю решений и итоговую стоимость.": (
        "A chat for every project: you can see the status, the decisions and "
        "the final price."
    ),
    "Поддержка после запуска": "Support after launch",
    "Обновляем, дорабатываем и следим за стабильностью — по запросу или по регламенту.": (
        "We update, extend and watch stability — on request or on a schedule."
    ),
    "Технологии": "Technologies",
    "Корпоративные сайты, лендинги и интернет-магазины": (
        "Corporate websites, landing pages and online stores"
    ),
    "Telegram-боты: заявки, оплата, интеграции с CRM": (
        "Telegram bots: requests, payments, CRM integrations"
    ),
    "Автоматизация рутинных процессов и отчётов": (
        "Automation of routine processes and reports"
    ),
    "Сквозная аналитика и отчётность": "End-to-end analytics and reporting",
    "Техническая поддержка и развитие продукта": "Technical support and product growth",
    "Знакомимся и уточняем задачу": "We get acquainted and clarify the task",
    "Готовим смету и план работ": "We prepare the estimate and the plan",
    "Разрабатываем и показываем прогресс": "We develop and show progress",
    "Тестируем, запускаем и передаём доступы": "We test, launch and hand over access",
    "Остаёмся на поддержке": "We stay for support",
    "Готовы обсудить задачу?": "Ready to discuss the task?",
    "Оставьте заявку — предложим решение и назовём сроки.": (
        "Send a request — we will propose a solution and a timeline."
    ),

    # --- Contact ----------------------------------------------------------
    "Оставить заявку ·": "Send a request ·",
    "Заявка": "Request",
    "Свяжитесь с нами": "Get in touch",
    "Расскажите о задаче — вернёмся с уточняющими вопросами и предложением в течение одного рабочего дня.": (
        "Tell us about the task — we will come back with questions and a "
        "proposal within one business day."
    ),
    "Имя": "Name",
    "Как к вам обращаться": "What should we call you",
    "E-mail": "E-mail",  # loanword: identical in both languages
    "— обязателен": "— required",
    "Ответим на этот адрес": "We will reply to this address",
    "Интересующая услуга": "Service you are interested in",
    "— Не выбрано / индивидуальный проект —": "— Not selected / custom project —",
    "Тема": "Subject",
    "Например: нужен Telegram-бот для приёма заявок": (
        "For example: we need a Telegram bot to take requests"
    ),
    "Описание задачи": "Task description",
    "Что нужно сделать, какие сроки и бюджет рассматриваете": (
        "What needs to be done, the timeline and the budget you have in mind"
    ),
    "До 5000 символов": "Up to 5000 characters",
    "Отправить заявку": "Send the request",
    "Заявка попадёт в поддержку — мы ответим на указанный e-mail.": (
        "The request goes to support — we will reply to the address you gave."
    ),
    "Можно также": "You can also",
    "войти": "sign in",
    "чтобы видеть историю обращений.": "to see the history of your requests.",

    # --- Support page -----------------------------------------------------
    "Служба поддержки ·": "Support ·",
    "Опишите вопрос — создадим тикет и ответим на указанный e-mail. Обычно отвечаем в течение одного рабочего дня.": (
        "Describe your question — we will create a ticket and reply to the "
        "address you gave. We usually answer within one business day."
    ),
    "Ваш e-mail": "Your e-mail",
    "Кратко о вопросе": "Briefly about the question",
    "Сообщение": "Message",
    "Опишите ситуацию подробнее": "Describe the situation in more detail",
    "Создать обращение": "Create a request",
    "Мои обращения": "My requests",
    "№": "No.",
    "Статус": "Status",
    "Создан": "Created",
    "Ответим на": "We will reply to",
    "Отвечаем в течение одного рабочего дня": "We answer within one business day",
    "Отправить обращение": "Send the request",
    "Отправляя форму, вы соглашаетесь с обработкой персональных данных.": (
        "By submitting the form you agree to the processing of personal data."
    ),
    "Не более 5000 символов": "Up to 5000 characters",
    "Не нашли ответ?": "Did not find an answer?",
    "Задайте вопрос напрямую — ответим в течение рабочего дня.": (
        "Ask us directly — we will reply within one business day."
    ),

    # --- FAQ --------------------------------------------------------------
    "Вопросы и ответы ·": "FAQ ·",
    "Ответы на частые вопросы о разработке сайтов, ботов и автоматизации в VA Digital Studio.": (
        "Answers to common questions about websites, bots and automation at "
        "VA Digital Studio."
    ),
    "Собрали то, что спрашивают чаще всего. Не нашли ответ — напишите нам.": (
        "We collected the most common questions. If yours is not here, write "
        "to us."
    ),
    "Поиск по вопросам…": "Search the questions…",
    "Поиск по вопросам": "Search the questions",
    "Найти": "Search",
    "Сбросить": "Reset",
    "Найдено:": "Found:",
    "По запросу «{query}» ничего не найдено.": "Nothing found for “{query}”.",
    "Не нашли ответ — напишите нам.": "Did not find an answer — write to us.",

    # --- Calculator -------------------------------------------------------
    "Рассчитайте примерную стоимость сайта, Telegram-бота или автоматизации за минуту.": (
        "Estimate the cost of a website, Telegram bot or automation in a minute."
    ),
    "Сколько будет стоить проект": "What the project will cost",
    "Ответьте на несколько вопросов — покажем ориентировочную стоимость и срок. Точную смету фиксируем после обсуждения задачи.": (
        "Answer a few questions and we will show an approximate cost and "
        "timeline. The exact estimate is fixed after we discuss the task."
    ),
    "Тип проекта": "Project type",
    "Объём работ": "Scope of work",
    "Сроки": "Timeline",
    "Дополнительно": "Extras",
    "Пересчитать": "Recalculate",
    "Примерная стоимость": "Approximate cost",
    "Из чего сложилась цена": "How the price breaks down",
    "Это ориентир, а не оферта. Итоговую смету согласуем в чате.": (
        "This is a guide, not an offer. We agree the final estimate in the chat."
    ),
    "Обсудить проект": "Discuss the project",
    "день": "day",
    "дня": "days",
    "дней": "days",
    "Одностраничный сайт": "Single-page website",
    "Многостраничный сайт": "Multi-page website",
    "Telegram-бот": "Telegram bot",
    "Базовый объём": "Basic scope",
    "Расширенный": "Extended",
    "Максимальный": "Maximum",
    "Спокойно, есть время": "Relaxed, no rush",
    "Стандартные сроки": "Standard timeline",
    "Срочно": "Urgent",
        "Тексты и наполнение": "Copy and content",
    "Интеграции (CRM, оплата)": "Integrations (CRM, payments)",
    "Поддержка 3 месяца": "3 months of support",

    # --- Portfolio --------------------------------------------------------
    "Портфолио ·": "Portfolio ·",
    "Кейсы VA Digital Studio: сайты, Telegram-боты и автоматизация с реальными результатами.": (
        "VA Digital Studio cases: websites, Telegram bots and automation with "
        "real results."
    ),
    "Кейсы и результаты": "Cases and results",
    "от лендингов до автоматизации. Показываем задачу, решение и результат.": (
        "from landing pages to automation. We show the task, the solution and "
        "the result."
    ),
    "Кейсы скоро появятся": "Cases are coming soon",
    "Мы готовим подборку выполненных проектов. Пока посмотрите услуги студии.": (
        "We are preparing a selection of completed projects. In the meantime, "
        "have a look at our services."
    ),
    "Клиент:": "Client:",
    "Что сделали": "What we did",
    "Открыть проект ↗": "Open the project ↗",
    "Хотите похожий проект?": "Want a similar project?",
    "Расскажите о задаче — предложим решение и сроки.": (
        "Tell us about the task — we will propose a solution and a timeline."
    ),
    "Смотреть услугу": "View the service",
    "Рассчитать стоимость": "Estimate the cost",
    "Похожие проекты": "Similar projects",

    # --- Reviews ----------------------------------------------------------
    "Отзывы ·": "Reviews ·",
    "Отзывы клиентов VA Digital Studio о сайтах, ботах и автоматизации.": (
        "VA Digital Studio client reviews about websites, bots and automation."
    ),
    "Что говорят клиенты": "What clients say",
    "Пока нет опубликованных отзывов — станьте первым.": (
        "No published reviews yet — be the first."
    ),
    "из 5.": "out of 5.",
    "Отзывов пока нет": "No reviews yet",
    "Оставьте свой — он появится на сайте после проверки модератором.": (
        "Leave yours — it will appear on the site after moderation."
    ),
    "Имя *": "Name *",
    "Компания или роль": "Company or role",
    "Студия ремонта": "Renovation studio",
    "Оценка *": "Rating *",
    "Текст отзыва *": "Review text *",
    "Что понравилось, как прошла работа…": "What you liked, how the work went…",
    "Отправить отзыв": "Send the review",
    "Отзыв появится на сайте после проверки модератором.": (
        "The review will appear on the site after moderation."
    ),
    "Оценка {rating} из 5": "Rating {rating} out of 5",

    # --- News -------------------------------------------------------------
    "Новости ·": "News ·",
    "Что нового": "What is new",
    "Обновления, кейсы и заметки команды VA Digital Studio.": (
        "Updates, cases and notes from the VA Digital Studio team."
    ),
    "Читать": "Read",
    "Поставить лайк": "Like",
    "Все новости": "All news",
    "Другие новости": "More news",
    "Назад к новостям": "Back to news",

    # --- Sign-in and registration -----------------------------------------
    "Вход —": "Sign in —",
    "Войдите в личный кабинет VA Digital Studio: e-mail и пароль, Telegram или Google.": (
        "Sign in to your VA Digital Studio account: e-mail and password, "
        "Telegram or Google."
    ),
    "Вход в аккаунт": "Sign in",
    "E-mail и пароль — основной способ. Ниже можно войти через Telegram или Google.": (
        "E-mail and password is the main way. Below you can sign in with "
        "Telegram or Google."
    ),
    "E-mail или логин": "E-mail or username",
    "you@example.com или ваш логин": "you@example.com or your username",
    "Пароль": "Password",
    "Ваш пароль": "Your password",
    "Нет аккаунта?": "No account?",
    "✈️ Войти через Telegram": "✈️ Sign in with Telegram",
    "Продолжить с Google": "Continue with Google",
    "или": "or",
    "или быстрее": "or faster",
    "Регистрация —": "Create an account —",
    "Создайте аккаунт VA Digital Studio по e-mail и паролю — заказывайте сайты, ботов и автоматизацию.": (
        "Create a VA Digital Studio account with an e-mail and password — "
        "order websites, bots and automation."
    ),
    "Регистрация": "Create an account",
    "Создайте аккаунт, чтобы отслеживать заказы и переписываться со студией.": (
        "Create an account to track orders and talk to the studio."
    ),
    "Логин": "Username",
    "например, ivan_dev": "for example, ivan_dev",
    "3–32 символа: латинские буквы, цифры, точка, дефис, подчёркивание": (
        "3–32 characters: Latin letters, digits, dot, hyphen, underscore"
    ),
    "Минимум 8 символов, буквы и цифры": "At least 8 characters, letters and digits",
    "Минимум 8 символов, должны быть буквы и цифры": (
        "At least 8 characters, must contain letters and digits"
    ),
    "Повторите пароль": "Repeat the password",
    "Ещё раз": "Once more",
    "Создать аккаунт": "Create the account",
    "Уже есть аккаунт?": "Already have an account?",
    "Telegram-вход": "Telegram sign-in",
    "Вход через Telegram": "Sign in with Telegram",
    "Отправить код в Telegram": "Send the code to Telegram",
    "Код из Telegram": "The code from Telegram",
    "Подтвердить": "Confirm",
    "Назад ко входу": "Back to sign in",

    # --- Profile, orders, chat --------------------------------------------
    "Баланс": "Balance",
    "Заказы": "Orders",
    "У вас пока нет заказов": "You have no orders yet",
    "Открыть": "Open",
    "Чат по заказу": "Order chat",
    "Отправить": "Send",
    "Написать сообщение…": "Write a message…",
    "Заказ": "Order",
    "Цена": "Price",
    "Итого": "Total",
    "Дата": "Date",
    "Действия": "Actions",
    "Все заказы": "All orders",
    "Сообщения": "Messages",
    "печатает…": "is typing…",

    # --- Errors -----------------------------------------------------------
    "Ошибка": "Error",
    "Требуется вход": "Sign-in required",
    "Доступ запрещён": "Access denied",
    "Страница не найдена": "Page not found",
    "Что-то пошло не так": "Something went wrong",
    "У вас нет прав для просмотра этой страницы": (
        "You do not have permission to view this page"
    ),
    "Войдите через Google, чтобы продолжить": "Sign in with Google to continue",
    "Отзыв опубликован": "Review published",
    "Отзыв отклонён и удалён": "Review rejected and deleted",
    "Неизвестный статус": "Unknown status",
    "Спасибо за отзыв! Он появится на сайте после проверки модератором.": (
        "Thank you for the review! It will appear on the site after moderation."
    ),
    "Заявка отправлена. Мы ответим на указанный e-mail.": (
        "The request has been sent. We will reply to the address you gave."
    ),
    "Обращение создано. Мы ответим на указанный e-mail.": (
        "The request has been created. We will reply to the address you gave."
    ),
    "Сообщение отправлено": "Message sent",

    "Такой страницы не существует": "This page does not exist",
    "На главную": "Go to the home page",

    # --- FAQ content ------------------------------------------------------
    "Общее": "General",
    "Оплата": "Payment",
    "Процесс": "Process",
    "Сколько стоит разработка сайта?": "How much does a website cost?",
    "Стоимость зависит от объёма. Одностраничный сайт начинается от 500 ₽, многостраничный — от 5 000 ₽. Точную смету фиксируем после обсуждения задачи: в калькуляторе можно получить ориентир за минуту.": (
        "The cost depends on the scope. A single-page site starts at 500 ₽, a "
        "multi-page website at 5,000 ₽. We fix the exact estimate after we "
        "discuss the task; the calculator gives you a guide in a minute."
    ),
    "Сколько времени занимает проект?": "How long does a project take?",
    "Типовой одностраничный сайт — от 2 дней, многостраничный — от 7 дней, Telegram-бот — от 2 дней, автоматизация скриптов — от 1 дня. Сроки фиксируем на старте и держим вас в курсе на каждом этапе.": (
        "A typical single-page site takes from 2 days, a multi-page site from "
        "7 days, a Telegram bot from 2 days, script automation from 1 day. We fix "
        "the timeline at the start and "
        "keep you informed at every stage."
    ),
    "Как проходит работа над проектом?": "How does the work go?",
    "Начинаем с обсуждения задачи в чате по заказу. Затем фиксируем состав работ и стоимость, показываем промежуточные результаты и сдаём проект с доступами. Все этапы видны в личном кабинете.": (
        "We start by discussing the task in the order chat. Then we fix the "
        "scope and the price, show intermediate results and deliver the project "
        "with access. Every stage is visible in your account."
    ),
    "Нужна ли предоплата?": "Is a prepayment required?",
    "Для небольших проектов работаем по факту сдачи. Для крупных разбиваем оплату на этапы: часть на старте, часть по готовности. Условия всегда согласуем заранее.": (
        "For small projects we work on delivery. For larger ones we split the "
        "payment into stages: part at the start, part on completion. We always "
        "agree the terms in advance."
    ),
    "Что входит в поддержку после запуска?": "What does post-launch support include?",
    "Мы не исчезаем после сдачи: следим за работой проекта, исправляем ошибки и помогаем с доработками. Первый месяц поддержки по мелким правкам входит в стоимость.": (
        "We do not disappear after delivery: we monitor the project, fix bugs "
        "and help with changes. The first month of support for small fixes is "
        "included in the price."
    ),
    "Работаете ли вы с готовыми сайтами?": "Do you work with existing websites?",
    "Да. Можем доработать существующий сайт, ускорить загрузку, подключить бота или автоматизацию к текущему проекту — даже если он сделан не нами.": (
        "Yes. We can extend an existing website, speed up loading, or connect a "
        "bot or automation to your current project — even if we did not build it."
    ),
    "Кому принадлежат исходники и доступы?": "Who owns the source code and access?",
    "Вам. После сдачи передаём доступы к хостингу, домену и репозиторию. Вы не привязаны к нам и можете развивать проект с любой командой.": (
        "You do. After delivery we hand over access to the hosting, the domain "
        "and the repository. You are not tied to us and can grow the project "
        "with any team."
    ),
    "Можно ли доработать проект после сдачи?": "Can the project be extended after delivery?",
    "Конечно. Небольшие правки делаем в рамках поддержки, крупные доработки оформляем отдельной задачей с понятной оценкой по срокам и стоимости.": (
        "Of course. Small fixes fall under support; larger changes become a "
        "separate task with a clear estimate of time and cost."
    ),

    # --- Account, orders and chat -----------------------------------------
    "Чаты": "Chats",
    "Управление заказом": "Order management",
    "Детали заказа": "Order details",
    "Загружаем историю сообщений…": "Loading message history…",
    "Аналитика": "Analytics",
    "Разработка": "Development",
    "Запуск": "Launch",
    "← Вернуться ко входу": "← Back to sign-in",
    "Откройте бота": "Open the bot",
    "Продолжить в Telegram": "Continue with Telegram",
    "Новостей пока нет": "No news yet",
    "Скоро расскажем о новых проектах и обновлениях студии.": (
        "We will soon share new projects and studio updates."
    ),
    "Описание пока не заполнено — обсудите детали с менеджером в чате.": (
        "The description is not filled in yet — discuss the details with the "
        "manager in the chat."
    ),
    "Обсудите детали, сроки и итоговую стоимость с менеджером.": (
        "Discuss the details, timeline and final price with the manager."
    ),
    "Стоимость": "Price",
    "Итоговая цена ещё не согласована — менеджер укажет её после обсуждения.": (
        "The final price is not agreed yet — the manager will set it after "
        "the discussion."
    ),
    "Номер": "Number",
    "Услуга": "Service",
    "Обновлён": "Updated",
    "💬 Связаться с менеджером": "💬 Contact the manager",
    "+ Новый заказ": "+ New order",
    "Чат": "Chat",
    "Заказов пока нет": "No orders yet",
    "Выберите услугу — мы создадим заказ и откроем чат с менеджером.": (
        "Pick a service — we will create an order and open a chat with the manager."
    ),
    "Перейти в каталог": "Go to the catalog",
    "Проверьте форму:": "Check the form:",
    "Администратор": "Administrator",
    "Пополнить баланс": "Top up balance",
    "всего заказов": "orders in total",
    "в работе": "in progress",
    "завершено": "completed",
    "История заказов": "Order history",
    "Выберите услугу в каталоге — мы создадим заказ и откроем чат с менеджером.": (
        "Pick a service in the catalog — we will create an order and open a "
        "chat with the manager."
    ),
    "Пополнение баланса": "Balance top-up",
    "Интеграция платёжной системы в разработке.": (
        "Payment integration is under development."
    ),
    "Пока можно оплатить по счёту — напишите менеджеру в чате заказа.": (
        "For now you can pay by invoice — message the manager in the order chat."
    ),
    "Понятно": "Got it",
    "Откройте бота {handle} и нажмите Start. Бот пришлёт код — введите его здесь.": (
        "Open the bot {handle} and press Start. The bot will send a code — "
        "enter it here."
    ),
    "Укажите e-mail, который будет привязан к аккаунту, затем нажмите Start в боте — он пришлёт код.": (
        "Enter the e-mail to link to your account, then press Start in the "
        "bot — it will send a code."
    ),

    "и нажмите Start. Бот пришлёт код — введите его здесь.": (
        "and press Start. The bot will send a code — enter it here."
    ),
    "пока не настроен на этом сервере.": "is not configured on this server yet.",
    "другим способом": "another way",
    "Войдите в VA Digital Studio через Telegram-бота: бот пришлёт код для входа.": (
        "Sign in to VA Digital Studio with the Telegram bot: the bot will send "
        "a sign-in code."
    ),

    # --- Counted nouns (the ``plural`` filter picks a form) ---------------
    "услуга": "service",
    "услуги": "services",
    "услуг": "services",
    "отзыв": "review",
    "отзыва": "reviews",
    "отзывов": "reviews",
    "отзыву": "review",
    "отзывам": "reviews",
    "проект": "project",
    "проекта": "projects",
    "проектов": "projects",
    "лайк": "like",
    "лайка": "likes",
    "лайков": "likes",

    # --- Remaining interface strings --------------------------------------
    "создан": "created",
    "чат": "chat",
    "В студии с": "With the studio since",
    "последний вход": "last sign-in",
    "средняя оценка": "average rating",
    "Средняя оценка": "Average rating",
    "из 5": "out of 5",
    "по": "from",

    "с клиентом": "with the client",
    "с менеджером": "with the manager",
    "Индивидуальный проект": "Custom project",
    "сохраняются в истории заказа. Не отправляйте пароли и данные карт.": (
        "are kept in the order history. Do not send passwords or card details."
    ),
    "в каталоге": "in the catalog",
    "разработка сайтов": "website development",
    "автоматизация": "automation",

    "чата": "chat",
    "Напишите сообщение…": "Write a message…",
    "бота и получить код": "bot and get a code",
    "Опишите вопрос подробнее — так мы поможем быстрее": (
        "Describe the question in more detail — that helps us help you faster"
    ),

    # --- Dashboard ---------------------------------------------------------
    '+ Новая новость': '+ New article',
    '+ Новая услуга': '+ New service',
    '+ Новый кейс': '+ New case',
    'Все обращения': 'All tickets',
    'Выручка по завершённым': 'Revenue from completed',
    'Диалогов пока нет': 'No conversations yet',
    'Добавьте выполненный проект, чтобы показать его на сайте.': 'Add a finished project to show it on the site.',
    'Добавьте первую услугу, чтобы она появилась в каталоге.': 'Add your first service so it appears in the catalog.',
    'Допустимо простое форматирование: абзацы, списки, ссылки.': 'Simple formatting is allowed: paragraphs, lists, links.',
    'Завершено и отменено': 'Completed and cancelled',
    'Заголовок': 'Title',
    'Заголовок *': 'Title *',
    'Задача, решение, результат…': 'Task, solution, result…',
    'Заказов всего': 'Orders in total',
    'Заказов пока нет.': 'No orders yet.',
    'Заказы не найдены': 'No orders found',
    'Закрытые': 'Closed',
    'Запустили новый сервис': 'We launched a new service',
    'Заявки не теряются': 'No requests are lost',
    'Здесь появятся заявки из формы «Служба поддержки».': 'Tickets from the “Support” form will appear here.',
    'Здравствуйте! Спасибо за обращение…': 'Hello! Thanks for reaching out…',
    'Изменить': 'Edit',
    'Изменить кейс': 'Edit case',
    'Изменить новость': 'Edit article',
    'Изменить услугу': 'Edit service',
    'Иконка (эмодзи)': 'Icon (emoji)',
    'История сообщений': 'Message history',
    'Итоговая стоимость': 'Final price',
    'Как только клиент напишет в чат по заказу, диалог появится здесь.': 'As soon as a client writes in an order chat, the conversation will appear here.',
    'Кейс': 'Case',
    'Кейсов пока нет': 'No cases yet',
    'Кейсы': 'Cases',
    'Клиент': 'Client',
    'Короткое описание для карточки на главной': 'Short description for the card on the home page',
    'Краткое описание': 'Short description',
    'Лайки': 'Likes',
    'Лендинг для студии ремонта': 'Landing page for a renovation studio',
    'Лендинги, корпоративные сайты и интернет-магазины': 'Landing pages, corporate sites and online stores',
    'Меньше — выше в каталоге.': 'Lower goes higher in the catalog.',
    'Название': 'Name',
    'Название *': 'Name *',
    'Название кейса *': 'Case name *',
    'Необязательно. Slug услуги из каталога.': 'Optional. The service slug from the catalog.',
    'Непрочитанных сообщений': 'Unread messages',
    'Нет отзывов на модерации': 'No reviews awaiting moderation',
    'Новая': 'New',
    'Новая новость': 'New article',
    'Новая услуга': 'New service',
    'Новые отзывы появятся здесь и уйдут на сайт после проверки.': 'New reviews will appear here and go to the site after moderation.',
    'Новый': 'New',
    'Новый кейс': 'New case',
    'Обзор': 'Overview',
    'Обложка (эмодзи)': 'Cover (emoji)',
    'Обновлено': 'Updated',
    'Обращений нет': 'No tickets',
    'Обращения в поддержку': 'Support tickets',
    'Описание кейса': 'Case description',
    'Описание не заполнено.': 'Description is empty.',
    'Опубликован': 'Published',
    'Опубликована': 'Published',
    'Опубликована в каталоге': 'Published in the catalog',
    'Опубликованные': 'Published',
    'Опубликованных отзывов пока нет.': 'No published reviews yet.',
    'Опубликовать': 'Publish',
    'Опубликуйте первую новость — она появится на главной и в разделе «Новости».': 'Publish your first article — it will appear on the home page and in the “News” section.',
    'Ответ клиенту': 'Reply to the client',
    'Ответ отправлен': 'Reply sent',
    'Ответьте клиенту…': 'Reply to the client…',
    'Отклонить': 'Reject',
    'Открытые': 'Open',
    'Открытые обращения': 'Open tickets',
    'Открытых обращений': 'Open tickets',
    'Открытых обращений нет.': 'No open tickets.',
    'Открыть заново': 'Reopen',
    'Открыть на сайте ↗': 'Open on the site ↗',
    'Открыть чат': 'Open chat',
    'Отмена': 'Cancel',
    'Отправитель': 'Sender',
    'Отправить ответ': 'Send reply',
    'Переписка': 'Thread',
    'Поиск заказов': 'Search orders',
    'Поиск: клиент, тема, описание': 'Search: client, subject, description',
    'Показывать в блоке «Топ»': 'Show in the “Top” block',
    'Показывать в подборке (топ)': 'Show in the featured (top) list',
    'Полное описание': 'Full description',
    'Полный текст…': 'Full text…',
    'Пользователей': 'Users',
    'Пользователь': 'User',
    'Портфолио (кейсы)': 'Portfolio (cases)',
    'Порядок сортировки': 'Sort order',
    'Последнее сообщение': 'Last message',
    'Последние заказы': 'Recent orders',
    'Превью': 'Preview',
    'Пусто — соберём из заголовка.': 'Empty — we will build it from the title.',
    'Пусто — соберём из названия автоматически.': 'Empty — we will build it from the name automatically.',
    'Пусто — соберём из названия.': 'Empty — we will build it from the name.',
    'Пустое поле сбрасывает цену. Клиент увидит изменение в чате.': 'An empty field clears the price. The client will see the change in the chat.',
    'Разделы дашборда': 'Dashboard sections',
    'Результат': 'Result',
    'Результат (метрика)': 'Result (metric)',
    'Сбросить фильтры': 'Reset filters',
    'Связанная услуга (slug)': 'Related service (slug)',
    'Скрыта': 'Hidden',
    'Смотреть все': 'View all',
    'Снять с публикации': 'Unpublish',
    'Создано': 'Created',
    'Создать кейс': 'Create case',
    'Создать новость': 'Create article',
    'Создать услугу': 'Create service',
    'Сообщение клиенту': 'Message to the client',
    'Сообщения видны клиенту мгновенно.': 'The client sees messages instantly.',
    'Сообщения сохраняются в истории заказа. Не отправляйте персональные данные.': 'Messages are kept in the order history. Do not send personal data.',
    'Сохранить изменения': 'Save changes',
    'Сохранить статус': 'Save status',
    'Сохранить цену': 'Save price',
    'Срок, дней': 'Duration, days',
    'Ссылка на проект': 'Project link',
    'Статус заказа': 'Order status',
    'Студия ремонта квартир': 'Apartment renovation studio',
    'Теги': 'Tags',
    'Теги (через запятую)': 'Tags (comma-separated)',
    'Текст новости': 'Article text',
    'Удалить': 'Delete',
    'Удалён': 'Deleted',
    'Услуг пока нет': 'No services yet',
    'Цена от': 'Price from',
    'Цена от, ₽': 'Price from, ₽',
    'Чат с клиентом': 'Chat with the client',
    'Чаты по заказам': 'Order chats',
    'Через запятую. Показываются как чипы в каталоге.': 'Comma-separated. Shown as chips in the catalog.',
    'Что входит в услугу, этапы работы, результат…': 'What the service includes, the stages of work, the result…',
    'Что сделали и какой результат получил клиент': 'What we did and what result the client got',
    'диалог': 'conversation',
    'диалогов': 'conversations',
    'заказ': 'order',
    'заказов': 'orders',
    'лендинг, cms, seo': 'landing, cms, seo',
    'лендинг, адаптив, Telegram': 'landing, responsive, Telegram',
    'например 45000': 'for example 45000',
    'обращение': 'ticket',
    'обращений': 'tickets',
    '← К списку': '← Back to the list',

    "кейс": "case",
    "услугу": "service",
    "новость": "article",
    "опубликовано": "published",
    "На модерации": "Awaiting moderation",
    "Оценка": "Rating",
    "и удалить": "and delete",
    "Обращение": "Ticket",
    "Ответ уйдёт на": "The reply will go to",
    "и закроет": "and close",
    "Аноним": "Anonymous",
    "Попробуйте изменить условия поиска": "Try changing the search terms",
    "сбросить фильтр": "reset the filter",
    "Как только клиент оформит": "As soon as a client places",
    "он появится здесь": "it will appear here",

    "диалога": "conversations",
    "заказа": "orders",
    "обращения": "tickets",

    # --- Service categories ----------------------------------------------
    "Сайты": "Websites",

    # --- Order and ticket statuses ---------------------------------------
    "Черновик": "Draft",
    "Обсуждение": "Discussion",
    "В работе": "In progress",
    "В разработке": "In development",
    "На проверке": "In review",
    "Завершён": "Completed",
    "Отменён": "Cancelled",
    "Открыт": "Open",
    "Закрыт": "Closed",
}

__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_COOKIE_NAME",
    "LOCALE_QUERY_PARAM",
    "SUPPORTED_LOCALES",
    "TRANSLATIONS",
    "count_label",
    "en_plural",
    "get_locale",
    "is_english",
    "normalize_locale",
    "other_locale",
    "plural",
    "set_locale",
    "t",
]
