# AGENTS.md — VA Digital Studio

## What this is

FastAPI + Jinja2 marketing/studio site (services catalogue, news, portfolio,
reviews, FAQ, cost calculator, orders/chat/support, admin dashboard).
SQLAlchemy 2.x ORM, Alembic migrations, SQLite by default and Postgres in
production. Russian-language UI, no SPA — progressive-enhancement JS only.

## Layout

- `app/main.py` — app factory; every router is registered here.
- `app/routes/` — `pages` (public marketing), `catalog`, `news`, `portfolio`,
  `reviews`, `faq`, `auth`, `login`, `profile`, `chat`, `admin` (prefix
  `/dashboard`).
- `app/services/` — business logic; routes stay thin.
- `app/models/` — SQLAlchemy models; `app/schemas/` — Pydantic forms/DTOs.
- `app/templates/` — Jinja templates; `partials/` holds header/burger/footer.
- `app/static/css/` — `base`, `components`, `layout`; design tokens in `:root`.
- `migrations/versions/` — Alembic revisions. Never hand-edit an applied one.
- `app/seed.py` — `seed_*` functions plus `bootstrap()`, the startup hook.
- `start.sh` — production entrypoint: `alembic upgrade head` then serve.

## Commands

```bash
python -m pytest -q                  # full suite (~254 tests)
python -m alembic revision --autogenerate -m "..."   # new migration
python -m alembic upgrade head       # apply migrations
python -m app.seed --bootstrap       # seed empty tables + promote admins
python -m app.seed --reset           # wipe and reseed content (destructive)
uvicorn app.main:app --reload        # local dev server
```

## Conventions

- **Mutations are POST-only** and every POST form must include
  `csrf_token` (hidden field) plus the `va_csrf` double-submit cookie.
  Tests fetch `/` first, then read `client.cookies.get("va_csrf")`.
- Admin routes are gated by `CurrentAdmin`; dashboard nav badges come from
  `attach_nav_counts` in `app/routes/admin.py` and are exposed through
  `app/templating.py`. Add a badge in both places.
- `app/templating.py` `render()` injects the common context (`path`,
  `current_user`, `is_admin`, csrf, nav counts). Add shared template
  variables there, not per route.
- Admin-authored HTML is sanitised on save (`app/security/sanitize.py`) and
  rendered with `| safe`.
- Money is `Decimal`; format with the `money` Jinja filter. Russian
  pluralisation uses the `plural` filter; dates use `date_ru` / `datetime_ru`.

## Deployment (Render)

Hosting is **Render**, decided by the user. Key facts learned the hard way:

- **`plan: free` is what keeps the deploy card-free.** A paid plan
  (`starter`, etc.) is what makes Render demand a payment method and a $1
  verification hold. Both the web service and the database are `free` in
  `render.yaml`.
- Free web services **spin down after 15 minutes** idle and take ~1 minute to
  wake. Free Postgres **expires 30 days** after creation.
- Free tier has **no Shell**, so content cannot be seeded by hand. That is why
  `start.sh` runs `python -m app.seed --bootstrap` on every boot; each table is
  seeded only when empty, so redeploys never overwrite dashboard edits.
- `render.yaml` is a Blueprint: Dashboard → New → Blueprint → pick the repo.
  Secrets marked `sync: false` (Google OAuth, ADMIN_EMAILS) are prompted for in
  the dashboard and never stored in git.
- `BASE_URL` is derived from `RENDER_EXTERNAL_URL`; set it explicitly only for
  a custom domain. `DATABASE_URL` is injected from the managed database.

## E-mail (Gmail SMTP)

Sign-in codes and support replies go out over SMTP (`app/services/mailer.py`).

- **Unconfigured SMTP means no e-mail, not a silent log.** In production
  `_deliver` returns `False` and logs the recipient only; the code is never
  written to the deploy log. Development still logs the body so a developer can
  read the code. `tests/test_mailer.py` guards both behaviours.
- **Never log the subject or body of a message.** `send_login_code` puts the
  code in the subject (`Код для входа: 123456`), so logging it leaks the code.
- `settings.email_configured` requires host + sender **and**, when a username is
  set, a password. A username without a password cannot authenticate, so it
  counts as unconfigured and the UI says so.
- The UI is honest about this: `/auth/login` hides the code button, and
  `/auth/code` explains the problem instead of claiming a message was sent
  (`_EMAIL_UNAVAILABLE` in `app/routes/login.py`).
- Gmail needs an **App Password** (16 chars, requires 2-Step Verification), not
  the account password. Port 587/STARTTLS. `render.yaml` already sets
  `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`; only `SMTP_PASSWORD` is prompted for.

## Git

- Default branch: `main`. Feature work goes on a branch and is merged back.
- The CI `GITHUB_TOKEN` in this environment is a **read-only** GitHub App
  installation token (`403 Resource not accessible by integration`). Pushing
  requires a classic PAT with `repo` scope.
