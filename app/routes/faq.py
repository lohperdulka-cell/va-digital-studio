"""FAQ page with server-side search, and the cost calculator."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.logging_config import get_logger
from app.schemas.reviews import CalculatorForm
from app.security.csrf import require_csrf
from app.services import estimator as estimator_service
from app.services import faq as faq_service
from app.templating import render

logger = get_logger(__name__)

# require_csrf is a no-op on GET, so it can guard the whole router.
router = APIRouter(tags=["faq"], dependencies=[Depends(require_csrf)])


@router.get("/faq")
def faq_page(
    request: Request,
    q: str = Query(default=""),
):
    query = (q or "").strip()
    items = faq_service.search(query) if query else faq_service.all_items()
    return render(
        request,
        "faq.html",
        {
            "items": items,
            "query": query,
            "grouped": None if query else faq_service.grouped(),
        },
    )


@router.get("/calculator")
def calculator_page(
    request: Request,
    project_type: str = Query(default="landing"),
    scope: str = Query(default="standard"),
    deadline: str = Query(default="normal"),
):
    """Render the calculator, optionally pre-filled from the query string.

    The estimate is computed on the server so the page works without
    JavaScript; the client-side script only makes it feel instant.
    """
    payload = CalculatorForm(
        project_type=project_type, scope=scope, deadline=deadline
    )
    result = estimator_service.estimate(
        project_type=payload.project_type,
        scope=payload.scope,
        deadline=payload.deadline,
    )
    return render(
        request,
        "calculator.html",
        {
            "project_types": estimator_service.project_types(),
            "scopes": estimator_service.scopes(),
            "deadlines": estimator_service.deadlines(),
            "addon_options": estimator_service.addon_options(),
            "selected": {
                "project_type": payload.project_type,
                "scope": payload.scope,
                "deadline": payload.deadline,
            },
            "estimate": result,
        },
    )


@router.post("/calculator")
async def calculator_submit(request: Request):
    """Recompute from a posted form so the result survives without JS."""
    raw = await request.form()
    addons = [str(item) for item in raw.getlist("addons")]
    payload = CalculatorForm(
        project_type=str(raw.get("project_type") or "landing"),
        scope=str(raw.get("scope") or "standard"),
        deadline=str(raw.get("deadline") or "normal"),
        addons=addons,
    )
    result = estimator_service.estimate(
        project_type=payload.project_type,
        scope=payload.scope,
        deadline=payload.deadline,
        addons=payload.addons,
    )
    return render(
        request,
        "calculator.html",
        {
            "project_types": estimator_service.project_types(),
            "scopes": estimator_service.scopes(),
            "deadlines": estimator_service.deadlines(),
            "addon_options": estimator_service.addon_options(),
            "selected": {
                "project_type": payload.project_type,
                "scope": payload.scope,
                "deadline": payload.deadline,
            },
            "selected_addons": payload.addons,
            "estimate": result,
        },
    )
