"""FAQ content and the search page."""

from __future__ import annotations

from app.services import faq as faq_service


def test_every_item_has_question_and_answer():
    for item in faq_service.all_items():
        assert item.question
        assert item.answer
        assert item.category in faq_service.CATEGORIES


def test_anchors_are_unique_and_url_safe():
    anchors = [item.anchor for item in faq_service.all_items()]
    assert len(anchors) == len(set(anchors))
    for anchor in anchors:
        assert anchor.startswith("faq-")
        assert " " not in anchor


def test_search_matches_question_and_answer():
    by_question = faq_service.search("предоплата")
    assert by_question, "expected a match on the prepayment question"

    by_answer = faq_service.search("исходники")
    assert by_answer, "expected a match inside an answer"


def test_search_is_case_insensitive_and_empty_returns_all():
    assert faq_service.search("СРОК") == faq_service.search("срок")
    assert faq_service.search("") == faq_service.all_items()


def test_grouped_covers_every_item():
    grouped = faq_service.grouped()
    total = sum(len(items) for items in grouped.values())
    assert total == len(faq_service.all_items())


def test_faq_page_renders_and_searches(client):
    page = client.get("/faq")
    assert page.status_code == 200
    assert "Частые вопросы" in page.text

    found = client.get("/faq", params={"q": "стоимость"})
    assert found.status_code == 200
    assert "Найдено" in found.text

    missing = client.get("/faq", params={"q": "ззззззз"})
    assert missing.status_code == 200
    assert "ничего не найдено" in missing.text
