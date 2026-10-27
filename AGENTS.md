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
python -m pytest -q                  # full suite (~363 tests)
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

## E-mail (support replies)

Sent from `app/services/mailer.py` over one of two transports.

- **Render's FREE web services cannot open outbound SMTP connections at all —
  ports 25, 465 and 587 are blocked by the platform.** Gmail SMTP therefore
  *cannot* work on the free plan; it fails at connect time. This is the
  documented cause of "codes never arrive" and it is not a code bug. Verified
  against Render's own docs (`render.com/llms-full.txt`, "Free web services
  can't send outbound network traffic on ports 25, 465, or 587").
- **The free-plan transport is an HTTP API over port 443**: `EMAIL_API_PROVIDER`
  (`brevo` or `resend`) plus `EMAIL_API_KEY`. Brevo allows 300/day free and
  only needs one verified sender address.
- SMTP remains for paid plans and local work; it is ignored when
  `EMAIL_API_PROVIDER` is set.
- **Unconfigured mail means no e-mail, not a silent log.** In production
  `_deliver` returns `False` and logs the recipient only; the body is never
  written to the deploy log. Development still logs the body so a developer can
  read it. `tests/test_mailer.py` guards both.
- **Never log the subject or body of a message.** Support replies carry
  private text; logging them would leak it.
- `settings.email_configured` is true when an HTTP API is configured, or when
  SMTP has host + sender and (if a username is set) a password.
- Mail is only used for support replies now. E-mail-code sign-in was removed
  because Render's free plan makes outbound mail unreliable; sign-in is
  e-mail+password, Google, or Telegram (`app/routes/login.py`).

## Administration

- `ADMIN_EMAILS` is authoritative: a listed address is an admin, an unlisted
  one is demoted on login/startup.
- **When `ADMIN_EMAILS` is empty, the OLDEST account becomes the owner.**
  Render's free plan has no Shell, so `python -m app.cli make_admin` cannot be
  run there; without this fallback nobody could reach `/dashboard`. Only the
  oldest account can be promoted, and only while no administrator exists.
  `accounts._apply_admin_policy` holds the rule; `seed.promote_admins` applies
  it at startup, the middleware on every request.
- `tests/test_bootstrap.py` covers the fallback, the "second visitor stays a
  visitor" case, and that an explicit `ADMIN_EMAILS` still wins.

## Sign-in

- The sign-in field is a single **login**: an e-mail address or the `username`
  chosen at registration (`accounts.find_by_login` decides by the `@`).
- `username` is stored lower-cased and unique; it is NULL for Google-only and
  Telegram-only accounts, which sign in with their e-mail.
- Registration requires `username`, `email`, `password`, `password_confirm`.
  `UsernameTakenError` and `EmailTakenError` are reported to the user on
  purpose — the rate limiter blunts enumeration.

## Catalogue (services and pricing)

- Three categories only: `sites`, `bots`, `automation`. The `design` bucket was
  removed; migration `b2c3d4e5f6a7` deletes any leftover `DESIGN` rows, because
  the narrowed Python enum would raise on reading one back.
- Prices run from a 500 ₽ single-page site to a 5,000 ₽ multi-page site.
  `app/services/estimator.py` mirrors the catalogue entry points, and
  `app/services/faq.py` quotes the same numbers in prose — keep the three in
  sync when a price changes.

## Languages (RU / EN)

- **Russian is the source of truth.** `app/i18n.py` holds one catalogue keyed by
  the Russian text; `t()` returns the key unchanged for `ru`, so a missing
  entry degrades to Russian instead of raising.
- `app/middleware.py` `_resolve_locale()` decides the locale in this order:
  `?lang=` → the `va_lang` cookie → Russian. Every response attaches it, so the
  choice survives navigation and is remembered for `LOCALE_COOKIE_MAX_AGE`.
- Templates translate by wrapping text in `t(...)`. The header and the burger
  menu carry the switcher; `locale_switch_url` keeps the current query string
  so a filtered catalog or a page number survives the switch.
- `plural(count, one, few, many)` takes the **three Russian forms** and picks
  the English singular/plural from the catalogue. Both English forms must be
  present, or a Russian noun leaks onto an English page.
- Flash messages are translated at render time in
  `app/templating.py:_translate_flashes()`.
- Tests: `tests/test_i18n.py`. It guards the catalogue (no duplicate keys, no
  empty values, no English value equal to the Russian source), the locale
  resolution order, the plural rule, and that public and dashboard pages render
  in both languages with no leftover Russian.

## Orders

- `app/services/orders.py` owns the status grouping. `ACTIVE_STATUSES` and
  `CLOSED_STATUSES` must stay a partition of `OrderStatus`: the client's
  "Мои заказы" tabs and the dashboard counters both rely on the two lists
  adding up to the total. `SUPPORT` belongs to the active side — its chat was
  reopened, so it is not finished.
- `/profile/orders` takes `?scope=all|active|closed`; anything else falls back
  to `all` so a stray query string still renders.

## Deployment status

- The site **is already deployed on Render** and has been running. Do not
  revisit hosting or payment-method topics; the card check is closed and is
  not part of any task.

## Git

- Default branch: `main`. Feature work goes on a branch and is merged back.
- The CI `GITHUB_TOKEN` in this environment is a **read-only** GitHub App
  installation token (`403 Resource not accessible by integration`). Pushing
  requires a classic PAT with `repo` scope.
