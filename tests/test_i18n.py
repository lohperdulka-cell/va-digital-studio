"""The RU/EN interface switch.

The catalogue is keyed by the Russian source string, so the tests that matter
are: Russian output is untouched (it is the default), English actually reaches
the page, the choice survives a navigation via the cookie, and every key in the
catalogue is reachable — a typo in a key would silently fall back to Russian.
"""

from __future__ import annotations

import re

import pytest

from app.i18n import (
    LOCALE_COOKIE_NAME,
    SUPPORTED_LOCALES,
    TRANSLATIONS,
    get_locale,
    normalize_locale,
    other_locale,
    set_locale,
    t,
)
from app.templating import plural


@pytest.fixture(autouse=True)
def _reset_locale():
    """Keep the ContextVar from leaking between tests."""
    set_locale("ru")
    yield
    set_locale("ru")


# --- The catalogue itself --------------------------------------------------


def test_catalogue_has_no_duplicate_keys():
    """A duplicate key in the literal would silently override the first entry."""
    import pathlib

    source = pathlib.Path("app/i18n.py").read_text(encoding="utf-8")
    start = source.index("TRANSLATIONS: dict[str, str] = {")
    end = source.index("\n}\n", start)
    keys = re.findall(r'^    "((?:[^"\\]|\\.)*)":', source[start:end], re.M)

    duplicates = {key for key in keys if keys.count(key) > 1}
    assert not duplicates, f"duplicate catalogue keys: {sorted(duplicates)}"


def test_every_translation_is_non_empty():
    empty = [key for key, value in TRANSLATIONS.items() if not value.strip()]
    assert not empty, f"empty translations: {empty}"


# Loanwords and proper nouns are spelled the same in both languages, so an
# identical value is correct for them and must not be read as a missing entry.
IDENTICAL_BY_DESIGN = {"E-mail"}


def test_english_values_are_not_the_russian_source():
    """An untranslated entry would make the switch look broken."""
    untranslated = [
        key
        for key, value in TRANSLATIONS.items()
        if value == key and key not in IDENTICAL_BY_DESIGN
    ]
    assert not untranslated, f"values identical to the key: {untranslated}"


# --- Lookup behaviour ------------------------------------------------------


def test_russian_returns_the_source_untouched():
    set_locale("ru")
    assert t("Каталог") == "Каталог"


def test_english_returns_the_translation():
    set_locale("en")
    assert t("Каталог") == "Catalog"


def test_unknown_text_falls_back_to_russian():
    set_locale("en")
    assert t("Строка, которой нет в каталоге") == "Строка, которой нет в каталоге"


def test_whitespace_is_normalised_before_lookup():
    """Templates wrap long sentences, so the key arrives with newlines."""
    set_locale("en")
    wrapped = "Наши услуги"
    assert t(wrapped) == "Our services"
    assert t("  Наши\n      услуги  ") == "Our services"


def test_placeholders_are_interpolated():
    set_locale("en")
    assert t("По запросу «{query}» ничего не найдено.", query="бот") == (
        "Nothing found for “бот”."
    )


def test_missing_placeholder_does_not_raise():
    set_locale("en")
    assert t("По запросу «{query}» ничего не найдено.") != ""


@pytest.mark.parametrize(
    "value,expected",
    [("en", "en"), ("EN", "en"), ("en-US", "en"), ("en_GB", "en"),
     ("ru", "ru"), ("RU-ru", "ru"), ("de", None), ("", None), (None, None)],
)
def test_normalize_locale(value, expected):
    assert normalize_locale(value) == expected


def test_other_locale_flips():
    set_locale("ru")
    assert other_locale() == "en"
    set_locale("en")
    assert other_locale() == "ru"


def test_default_locale_is_russian():
    set_locale(None)
    assert get_locale() == "ru"


def test_plural_switches_rule():
    set_locale("ru")
    assert plural(1, "услуга", "услуги", "услуг") == "услуга"
    assert plural(3, "услуга", "услуги", "услуг") == "услуги"
    assert plural(5, "услуга", "услуги", "услуг") == "услуг"

    set_locale("en")
    assert plural(1, "service", "services", "services") == "service"
    assert plural(3, "service", "services", "services") == "services"


@pytest.mark.parametrize(
    "count,forms,expected",
    [
        (1, ("услуга", "услуги", "услуг"), "service"),
        (3, ("услуга", "услуги", "услуг"), "services"),
        (1, ("отзыв", "отзыва", "отзывов"), "review"),
        (4, ("проект", "проекта", "проектов"), "projects"),
        (2, ("лайк", "лайка", "лайков"), "likes"),
        (1, ("день", "дня", "дней"), "day"),
        (5, ("день", "дня", "дней"), "days"),
    ],
)
def test_plural_translates_the_english_forms(count, forms, expected):
    """The filter takes Russian forms; English must not leak the Russian noun."""
    set_locale("en")
    assert plural(count, *forms) == expected


def test_every_plural_form_used_by_templates_is_translated():
    """A missing entry would print a Russian noun on an English page."""
    import pathlib

    forms: set[str] = set()
    for path in pathlib.Path("app/templates").rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"plural\(\s*'([^']*)',\s*'([^']*)',\s*'([^']*)'\s*\)", source
        ):
            forms.update(match.groups())

    missing = sorted(form for form in forms if form not in TRANSLATIONS)
    assert not missing, f"plural forms without a translation: {missing}"


# --- Over HTTP -------------------------------------------------------------


def test_home_page_is_russian_by_default(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'lang="ru"' in response.text
    assert "Главная" in response.text


def test_lang_query_switches_the_page_to_english(client):
    response = client.get("/?lang=en")
    assert response.status_code == 200
    assert 'lang="en"' in response.text
    assert "Home" in response.text
    assert "Главная" not in response.text


def test_lang_query_sets_a_cookie_so_the_choice_sticks(client):
    client.get("/?lang=en")
    # No ?lang= on the second request: the cookie must carry the choice.
    response = client.get("/catalog")
    assert 'lang="en"' in response.text


def test_cookie_can_be_overridden_back_to_russian(client):
    client.get("/?lang=en")
    response = client.get("/?lang=ru")
    assert 'lang="ru"' in response.text
    assert "Главная" in response.text


def test_unknown_lang_is_ignored(client):
    response = client.get("/?lang=de")
    assert 'lang="ru"' in response.text


def test_switch_link_keeps_other_query_parameters(client):
    """A filtered catalog must stay filtered after switching the language."""
    response = client.get("/catalog?category=bots&lang=ru")
    assert "lang=en" in response.text
    assert "category=bots" in response.text


@pytest.mark.parametrize(
    "path",
    ["/", "/catalog", "/portfolio", "/news", "/calculator", "/faq",
     "/about", "/reviews", "/contact", "/support", "/auth/login", "/auth/register"],
)
def test_public_pages_render_in_both_languages(client, path):
    for lang in SUPPORTED_LOCALES:
        response = client.get(f"{path}?lang={lang}")
        assert response.status_code == 200, f"{path}?lang={lang}"
        assert f'lang="{lang}"' in response.text


def test_service_category_labels_are_translated(client):
    english = client.get("/catalog?lang=en").text
    assert "Telegram bots" in english or "Websites" in english

    russian = client.get("/catalog?lang=ru").text
    assert "Telegram-боты" in russian or "Сайты" in russian


def test_faq_content_is_translated(client):
    english = client.get("/faq?lang=en").text
    assert "How much does a website cost?" in english

    russian = client.get("/faq?lang=ru").text
    assert "Сколько стоит разработка сайта?" in russian


def test_locale_cookie_name_is_stable():
    """Renaming it would silently log every visitor out of their choice."""
    assert LOCALE_COOKIE_NAME == "va_lang"


# --- Dashboard -------------------------------------------------------------

DASHBOARD_PATHS = [
    "/dashboard",
    "/dashboard/orders",
    "/dashboard/services",
    "/dashboard/cases",
    "/dashboard/reviews",
    "/dashboard/news",
    "/dashboard/support",
    "/dashboard/chats",
    "/dashboard/services/new",
    "/dashboard/cases/new",
    "/dashboard/news/new",
]

DASHBOARD_EN = {
    "/dashboard": ["Overview", "Orders", "Chats", "Support", "Services", "Cases", "Reviews", "News"],
    "/dashboard/services/new": ["New service", "Name", "Category", "Price from"],
    "/dashboard/cases/new": ["New case", "Case name", "Client"],
    "/dashboard/news/new": ["New article", "Title", "Preview"],
}

DASHBOARD_RU = ["Обзор", "Заказы", "Чаты", "Поддержка", "Услуги", "Кейсы", "Отзывы", "Новости"]


@pytest.mark.parametrize("path", DASHBOARD_PATHS)
def test_dashboard_renders_in_both_languages(client, login_as, make_user, path):
    admin = make_user("owner@example.com", is_admin=True)
    login_as(admin)

    for lang in SUPPORTED_LOCALES:
        response = client.get(f"{path}?lang={lang}")
        assert response.status_code == 200, f"{path}?lang={lang}"
        assert f'lang="{lang}"' in response.text


@pytest.mark.parametrize("path,labels", DASHBOARD_EN.items())
def test_dashboard_shows_english_labels(client, login_as, make_user, path, labels):
    login_as(make_user("owner@example.com", is_admin=True))

    body = client.get(f"{path}?lang=en").text
    missing = [label for label in labels if label not in body]
    assert not missing, f"{path}: {missing}"


def test_dashboard_navigation_is_translated(client, login_as, make_user):
    login_as(make_user("owner@example.com", is_admin=True))

    english = client.get("/dashboard?lang=en").text
    for label in DASHBOARD_EN["/dashboard"]:
        assert label in english, label

    russian = client.get("/dashboard?lang=ru").text
    for label in DASHBOARD_RU:
        assert label in russian, label


def test_dashboard_pages_have_no_leftover_russian_in_english(client, login_as, make_user):
    """The switcher label itself is Russian by design; everything else is not."""
    login_as(make_user("owner@example.com", is_admin=True))

    for path in DASHBOARD_PATHS:
        body = client.get(f"{path}?lang=en").text
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
        body = re.sub(r"<[^>]+>", " ", body)
        # "Русский" is the other-language label on the switch link.
        body = body.replace("Русский", "")
        leftover = sorted(set(re.findall(r"[А-Яа-яЁё][А-Яа-яЁё\-]{2,}", body)))
        assert not leftover, f"{path}: {leftover[:8]}"
