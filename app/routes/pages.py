"""Public marketing pages: home, about, contact."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.flash import flash
from app.logging_config import get_logger
from app.schemas import SupportTicketForm
from app.security.csrf import require_csrf
from app.security.deps import DbSession, OptionalUser
from app.services import catalog as catalog_service
from app.services import newsfeed as news_service
from app.services import support as support_service
from app.templating import render

logger = get_logger(__name__)

# require_csrf is a no-op on safe methods, so it can guard the whole router.
router = APIRouter(tags=["pages"], dependencies=[Depends(require_csrf)])

HOME_NEWS_LIMIT = 5
HOME_SERVICES_LIMIT = 6


@router.get("/")
def home(request: Request, db: DbSession):
    return render(
        request,
        "index.html",
        {
            "services": catalog_service.list_services(
                db, limit=HOME_SERVICES_LIMIT
            ),
            "news": news_service.list_news(db, limit=HOME_NEWS_LIMIT),
            "stats": catalog_service.home_stats(db),
        },
    )


@router.get("/about")
def about(request: Request):
    return render(request, "about.html")


@router.get("/contact")
def contact_page(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
):
    return render(
        request,
        "contact.html",
        {
            "services": catalog_service.list_services(db),
            "form": {},
            "errors": [],
        },
    )


@router.post("/contact")
def contact_submit(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
    name: str = Form(""),
    email: str = Form(""),
    subject: str = Form(""),
    message: str = Form(""),
    service_id: str = Form(""),
):
    """Validate the enquiry and turn it into a support ticket."""
    try:
        payload = SupportTicketForm(
            subject=subject,
            message=message,
            email=email or (user.email if user else None),
            name=name,
        )
    except ValidationError as exc:
        errors = _form_errors(exc)
        logger.info("Contact form rejected: %s", errors)
        return render(
            request,
            "contact.html",
            {
                "services": catalog_service.list_services(db),
                "form": {
                    "name": name,
                    "email": email,
                    "subject": subject,
                    "message": message,
                    "service_id": _as_int(service_id),
                },
                "errors": errors,
            },
            status_code=422,
        )

    ticket = support_service.create_ticket(
        db,
        subject=payload.subject,
        message=payload.message,
        email=str(payload.email or ""),
        name=payload.name,
        user=user,
    )

    chosen = _as_int(service_id)
    if chosen:
        service = catalog_service.get_service(db, chosen)
        if service is not None:
            logger.info(
                "Contact enquiry references service_id=%s (ticket=%s)",
                service.id,
                ticket.id,
            )

    flash(
        request,
        f"Заявка №{ticket.id} принята. Ответим на {ticket.email} в течение рабочего дня.",
        "success",
    )
    return RedirectResponse("/contact", status_code=303)


def _as_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _form_errors(exc: Exception) -> list[str]:
    """Turn a pydantic ValidationError into human-readable Russian strings."""
    errors: list[str] = []
    for error in getattr(exc, "errors", list)():
        field = error.get("loc", ("",))[-1]
        label = {
            "subject": "Тема",
            "message": "Сообщение",
            "email": "E-mail",
            "name": "Имя",
        }.get(str(field), str(field))
        errors.append(f"{label}: {error.get('msg', 'некорректное значение')}")
    return errors or ["Не удалось проверить данные формы"]


@router.get("/support")
def support_page(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
):
    return render(
        request,
        "support.html",
        {
            "form": {
                "email": user.email if user else "",
                "name": user.display_name if user else "",
            },
            "errors": [],
            "my_tickets": support_service.list_for_user(db, user.id) if user else [],
        },
    )


@router.post("/support")
def support_submit(
    request: Request,
    db: DbSession,
    user: OptionalUser = None,
    name: str = Form(""),
    email: str = Form(""),
    subject: str = Form(""),
    message: str = Form(""),
):
    """Ticket form used by the footer modal and the /support page."""
    try:
        payload = SupportTicketForm(
            subject=subject,
            message=message,
            email=email or (user.email if user else None),
            name=name,
        )
    except ValidationError as exc:
        errors = _form_errors(exc)
        logger.info("Support form rejected: %s", errors)
        return render(
            request,
            "support.html",
            {
                "form": {"name": name, "email": email, "subject": subject, "message": message},
                "errors": errors,
                "my_tickets": support_service.list_for_user(db, user.id) if user else [],
            },
            status_code=422,
        )

    ticket = support_service.create_ticket(
        db,
        subject=payload.subject,
        message=payload.message,
        email=str(payload.email or ""),
        name=payload.name,
        user=user,
    )
    flash(
        request,
        f"Обращение №{ticket.id} создано. Ответ придёт на {ticket.email}.",
        "success",
    )
    return RedirectResponse("/support", status_code=303)
