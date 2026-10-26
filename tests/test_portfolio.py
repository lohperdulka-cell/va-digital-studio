"""Portfolio: service queries, public pages and admin CRUD."""

from __future__ import annotations

from app.services import portfolio as portfolio_service


def _case_payload(slug: str = "case-one", **overrides) -> dict:
    payload = {
        "slug": slug,
        "title": "Кейс для теста",
        "client": "Клиент",
        "summary": "Короткое описание",
        "body": "<p>Текст</p>",
        "result_metric": "Результат",
        "cover_emoji": "🧩",
        "tags": ["тест"],
        "external_url": "",
        "service_slug": "",
        "is_published": True,
        "is_featured": False,
        "sort_order": 0,
    }
    payload.update(overrides)
    return payload


def test_create_and_list_published_cases(db):
    portfolio_service.create_case(db, _case_payload())
    cases = portfolio_service.list_cases(db)
    assert [case.slug for case in cases] == ["case-one"]


def test_draft_cases_are_hidden_from_the_public_list(db):
    portfolio_service.create_case(db, _case_payload(is_published=False))
    assert portfolio_service.list_cases(db) == []
    assert len(portfolio_service.list_all_cases(db)) == 1


def test_featured_cases_sort_first(db):
    portfolio_service.create_case(db, _case_payload(slug="a", sort_order=1))
    portfolio_service.create_case(
        db, _case_payload(slug="b", sort_order=2, is_featured=True)
    )
    cases = portfolio_service.list_cases(db)
    assert cases[0].slug == "b"


def test_update_and_delete_case(db):
    case = portfolio_service.create_case(db, _case_payload())
    portfolio_service.update_case(db, case, {"title": "Обновлено"})
    assert portfolio_service.get_case(db, case.id).title == "Обновлено"

    portfolio_service.delete_case(db, case)
    assert portfolio_service.get_case(db, case.id) is None


def test_slug_collision_is_resolved(db):
    portfolio_service.create_case(db, _case_payload(slug="dup"))
    second = portfolio_service.create_case(db, _case_payload(slug="dup"))
    assert second.slug != "dup"


def test_portfolio_pages_render(client, db):
    portfolio_service.create_case(db, _case_payload(slug="visible-case"))

    listing = client.get("/portfolio")
    assert listing.status_code == 200
    assert "Кейс для теста" in listing.text

    detail = client.get("/portfolio/visible-case")
    assert detail.status_code == 200
    assert "Кейс для теста" in detail.text


def test_unknown_case_is_404(client):
    assert client.get("/portfolio/nope").status_code == 404


def test_admin_requires_login(client):
    response = client.get("/dashboard/cases", follow_redirects=False)
    assert response.status_code in (302, 303, 401, 403)
