# VA Digital Studio

Full-stack сайт digital-студии: публичный каталог услуг, новости с лайками,
личный кабинет, заказы с чатом в реальном времени и админ-дашборд.

Стек: FastAPI + SQLAlchemy 2.x + Alembic + Jinja2, PostgreSQL (в dev — SQLite),
вход только через Google OAuth 2.0, сессия — JWT в httponly-cookie.

## Возможности

**Публичная часть**
- Главная с УТП, блоком услуг из БД и последними новостями (лайки по AJAX,
  один лайк на пользователя).
- Каталог услуг с фильтром по категориям (Сайты / Telegram-боты /
  Автоматизация / Дизайн) и страницами услуг.
- Форма заявки и модалка службы поддержки (создаёт тикет в БД).

**Личный кабинет (`/profile`)**
- Вход по e-mail **или логину** с паролем, плюс Google и Telegram.
- Данные профиля, баланс, история заказов, переход к заказу и чату.

**Заказы и чат**
- Черновик заказа создаётся со страницы услуги и ведёт в чат.
- WebSocket-чат по заказу (`/chat/{order_id}`): история из БД, доставка в
  реальном времени обеим сторонам, индикатор «печатает», системные
  сообщения о смене статуса и цены.

**Дашборд (`/dashboard`, только администратор)**
- Обзор со счётчиками, заказы (поиск, фильтр по статусу, смена статуса и
  итоговой цены), список чатов с превью и счётчиком непрочитанных,
  тикеты поддержки с ответом, CRUD услуг и новостей.

## Технологии

| Слой | Выбор |
| --- | --- |
| Backend | Python 3.11+, FastAPI, Uvicorn |
| ORM / миграции | SQLAlchemy 2.x, Alembic |
| БД | PostgreSQL (prod), SQLite (dev) |
| Шаблоны | Jinja2 (SSR) + Vanilla JS |
| Стили | Собственный CSS с переменными (без сборки и CDN) |
| Авторизация | Google OAuth 2.0 (authlib), JWT в httponly-cookie |
| Реалтайм | `fastapi.WebSocket` |
| Безопасность | CSRF (double-submit cookie), slowapi, bleach, security-заголовки |
| Тесты | pytest |

CSS написан вручную, а не через Tailwind: у проекта один статический набор
страниц, поэтому общий файл переменных и компонентов проще сопровождать, чем
подключать CDN-сборку, которая добавляет внешнюю зависимость на рантайме.

## Быстрый старт (локально)

Нужен Python 3.11+ (или Docker — см. следующий раздел). В dev-режиме
PostgreSQL не требуется: если `DATABASE_URL` пуст, используется SQLite.

```bash
git clone <repo-url> va_digital_studio
cd va_digital_studio

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # затем откройте .env и задайте SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(64))"   # вставьте вывод в SECRET_KEY

alembic upgrade head             # создать схему
python -m app.seed               # 4 услуги, 4 новости, назначить админов из ADMIN_EMAILS

uvicorn app.main:app --reload    # http://localhost:8000
```

Проверка живости: `GET /healthz` → `{"status":"ok"}`.

### Запуск через docker-compose

Поднимает PostgreSQL и приложение, применяет миграции при старте.

```bash
cp .env.example .env             # обязательно задайте SECRET_KEY (минимум 64 символа)
docker compose up --build        # http://localhost:8000
```

Что происходит внутри: контейнер `db` ждёт `pg_isready`, затем `app` выполняет
`alembic upgrade head` и запускает Uvicorn. Данные Postgres и логи лежат в
именованных томах `postgres_data` и `app_logs`.

Полезные команды:

```bash
docker compose logs -f app                       # логи приложения
docker compose exec app python -m app.seed       # залить демо-данные
docker compose exec app alembic upgrade head     # применить миграции вручную
docker compose down                              # остановить
docker compose down -v                           # остановить и удалить данные
```

Переменные для compose берутся из `.env`: `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB`, `APP_PORT`, `POSTGRES_PORT` (значения по умолчанию — в
`docker-compose.yml`).

## Настройка Google OAuth

Вход в систему — только через Google, поэтому без этих шагов кнопка «Войти
через Google» покажет страницу с ошибкой конфигурации.

1. Откройте [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials).
2. Создайте проект (или выберите существующий) и настройте
   **OAuth consent screen**: тип *External*, укажите название приложения,
   e-mail поддержки и добавьте себя в *Test users* (пока приложение не
   опубликовано).
3. **Create credentials → OAuth client ID → Web application**.
4. В **Authorized redirect URIs** добавьте ровно один адрес, совпадающий с
   `BASE_URL` из `.env`:

   | Окружение | Redirect URI |
   | --- | --- |
   | Локально | `http://localhost:8000/auth/callback` |
   | Docker | `http://localhost:8000/auth/callback` |
   | Прод | `https://ваш-домен/auth/callback` |

   Схема (`http`/`https`), хост, порт и путь должны совпадать посимвольно —
   иначе Google вернёт `redirect_uri_mismatch`.
5. Скопируйте **Client ID** и **Client secret** в `.env`:

   ```env
   GOOGLE_CLIENT_ID=1234567890-abcdef.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
   BASE_URL=http://localhost:8000
   ```

6. Перезапустите приложение. В логах при старте должна появиться строка
   `oauth=configured`; если там `oauth=NOT configured`, значит переменные не
   подхватились.

В продакшене дополнительно выставьте `COOKIE_SECURE=true` (cookie уйдёт только
по HTTPS) и задайте `BASE_URL` с реальным доменом.

## Как назначить администратора

Есть два независимых способа; они не конфликтуют, и `is_admin` выставляется
при каждом входе.

**1. Через `.env`** — подходит для команды, которая ещё не заходила в систему:

```env
ADMIN_EMAILS=you@gmail.com,admin@example.com
```

Любой пользователь, вошедший с таким e-mail, получает права администратора
автоматически. `python -m app.seed` дополнительно проставляет флаг уже
существующим в базе аккаунтам из списка.

**2. CLI-командой** — когда аккаунт уже создан после первого входа:

```bash
python -m app.cli make_admin user@example.com     # выдать права
python -m app.cli revoke_admin user@example.com   # снять права
python -m app.cli list_users                      # список пользователей
python -m app.cli whoami user@example.com         # данные одного пользователя
```

В Docker те же команды выполняются так:

```bash
docker compose exec app python -m app.cli make_admin user@example.com
```

Чтобы проверить, что права применились, войдите в аккаунт и откройте
`/dashboard` — в шапке появится пункт «Дашборд», а обычным пользователям этот
раздел отдаёт `403`.

## Команды

```bash
python -m app.seed --bootstrap        # старт: залить пустой каталог + синхронизировать админов
python -m app.seed                    # услуги, новости, админы из ADMIN_EMAILS
python -m app.seed --reset            # пересоздать демо-контент
python -m app.cli <команда>           # управление администраторами
alembic upgrade head                  # применить миграции
alembic revision --autogenerate -m "описание"   # новая миграция
uvicorn app.main:app --reload         # сервер разработки
pytest                                # тесты
ruff check .                          # линтер
```

## Структура проекта

```
va_digital_studio/
├── app/
│   ├── main.py              # точка входа FastAPI, middleware, обработчики ошибок
│   ├── config.py            # настройки (pydantic-settings, читает .env)
│   ├── database.py          # engine, SessionLocal, Base
│   ├── formatting.py        # общий формат денег (52 500 ₽)
│   ├── logging_config.py    # RotatingFileHandler → logs/app.log
│   ├── middleware.py        # security-заголовки, request-id
│   ├── templating.py        # общий Jinja2-окружение, фильтры, render()
│   ├── seed.py              # демо-данные
│   ├── cli.py               # make_admin / revoke_admin / list_users / whoami
│   ├── models/              # SQLAlchemy-модели
│   ├── schemas/             # Pydantic-схемы
│   ├── routes/              # auth, pages, services, orders, news, profile,
│   │                        # chat (WebSocket), support, admin
│   ├── services/            # бизнес-логика (orders, chat, dashboard, ...)
│   ├── security/            # sessions, csrf, rate-limit, sanitize, deps
│   ├── templates/           # Jinja2 (base, страницы, dashboard/, partials/)
│   └── static/              # css, js, img
├── migrations/              # Alembic
├── logs/                    # app.log (в .gitignore)
├── tests/                   # pytest
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
└── .env.example
```

## Маршруты

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/` | Главная: УТП, услуги, новости с лайками |
| GET | `/catalog` | Каталог с фильтром `?category=` |
| GET | `/catalog/{slug}` | Страница услуги, кнопка «Заказать» |
| GET | `/news`, `/news/{id}` | Лента и страница новости |
| POST | `/news/{id}/like` | Лайк (AJAX, нужен вход) |
| GET | `/about`, `/contact` | О студии, форма заявки |
| GET | `/support` | Форма обращения в поддержку |
| GET | `/auth/login` | Форма входа (e-mail/логин + пароль) |
| POST | `/auth/login` | Вход по e-mail или логину |
| GET | `/auth/register` | Форма регистрации (логин, e-mail, пароль) |
| POST | `/auth/register` | Создание аккаунта |
| GET | `/auth/google` | Старт Google OAuth |
| GET | `/auth/callback` | Обработка ответа Google |
| GET/POST | `/auth/telegram` | Вход через Telegram |
| POST | `/auth/logout` | Выход (сброс cookie) |
| GET | `/profile` | Личный кабинет |
| GET | `/profile/orders/{id}` | Детали заказа клиента |
| GET | `/chat/{order_id}` | Страница чата по заказу |
| WS | `/ws/chat/{order_id}` | WebSocket-чат |
| GET | `/dashboard` | Обзор (только админ) |
| GET | `/dashboard/orders` | Все заказы: поиск, фильтр по статусу |
| POST | `/dashboard/orders/{id}/status` | Смена статуса |
| POST | `/dashboard/orders/{id}/price` | Итоговая цена |
| GET | `/dashboard/chats` | Диалоги, превью, непрочитанные |
| GET | `/dashboard/support` | Тикеты поддержки |
| POST | `/dashboard/support/{id}/reply` | Ответ на тикет |
| GET | `/dashboard/services` | CRUD услуг |
| GET | `/dashboard/news` | CRUD новостей |
| GET | `/healthz` | Проверка живости |

## Безопасность

| Требование | Реализация |
| --- | --- |
| SQL-инъекции | Только ORM/SQLAlchemy, raw SQL с подстановкой строк не используется |
| XSS | Jinja2 autoescape включён; пользовательский текст очищается `bleach` (`app/security/sanitize.py`) до сохранения |
| CSRF | Double-submit cookie: `CsrfCookieMiddleware` выдаёт httponly-cookie `va_csrf`, `require_csrf` сверяет его с полем `csrf_token` формы или заголовком `X-CSRF-Token` для fetch-запросов |
| Rate limiting | `app/security/ratelimit.py`: 30 запросов/мин на IP для `/auth/*`, `/support`, `/contact`; WebSocket-чат — 30 сообщений/мин на пользователя |
| JWT | HS256, секрет из `.env`, проверяются `exp`, `iat`, `iss`, `sub` |
| Cookie | `httponly=True`, `samesite="lax"`, `secure` из `COOKIE_SECURE` (обязательно `true` в проде), срок 7 дней |
| OAuth state | Параметр `state` генерируется на входе и проверяется в callback |
| Валидация | Все входные данные проходят через Pydantic-схемы; длина сообщения чата ≤ 2000 символов, форма поддержки ≤ 5000 |
| Логи | `RotatingFileHandler` (5 МБ × 5) → `logs/app.log`; пишутся входы, ошибки, создание заказов и действия админа; пароли и токены не логируются |
| Security-заголовки | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, базовая CSP (`app/security/headers.py`) |
| Секреты | Только в `.env` (в `.gitignore`); `.env.example` содержит плейсхолдеры |
| Ошибки | Глобальный обработчик: пользователю — общее сообщение, детали — в лог |
| WebSocket | JWT из cookie проверяется в handshake; неавторизованных закрываем кодом 4401, чужие заказы — 4403 |

### Что нужно сделать перед продакшеном

- Сгенерировать случайный `SECRET_KEY` (≥ 64 символа) и выставить
  `COOKIE_SECURE=true`.
- Указать реальный `BASE_URL` с HTTPS и добавить его `/auth/callback` в
  Google Cloud Console.
- Ограничить `ADMIN_EMAILS` реальными адресами.
- Настроить отправку почты, иначе **коды для входа по почте не отправляются**, а
  письма поддержки только логируются. На бесплатном тарифе Render SMTP закрыт —
  нужен HTTP-API (`EMAIL_API_PROVIDER` + `EMAIL_API_KEY`). В проде код в лог не
  пишется: страница честно сообщает, что отправка не настроена. См. «Почта».
- CSP содержит `'unsafe-inline'` для `script-src`, потому что часть страниц
  использует инлайновые обработчики; для строгого CSP их нужно вынести в
  отдельные файлы и заменить директиву на nonce.

## Деплой на Render.com

Проект готов к выкладке как есть: `Dockerfile` и `render.yaml` уже в репозитории.

### Вариант 1 — Blueprint (инфраструктура как код)

1. Запушьте репозиторий на GitHub.
2. Render Dashboard → **New** → **Blueprint** → выберите репозиторий.
3. Render прочитает `render.yaml`, создаст базу `va-studio-db` и веб-сервис
   `va-digital-studio`.
4. Вас попросят заполнить переменные, помеченные `sync: false`:
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS` (и, если нужна
   почта, `SMTP_*`). `SECRET_KEY` Render сгенерирует сам.
5. После первого деплоя скопируйте публичный адрес сервиса и добавьте
   `https://<имя>.onrender.com/auth/callback` в Google Cloud Console →
   Credentials → Authorized redirect URIs.

### Вариант 2 — вручную

1. **New** → **PostgreSQL**, план `free` или выше. Скопируйте **Internal
   Database URL**.
2. **New** → **Web Service** → репозиторий → Runtime: **Docker**.
3. Health Check Path: `/healthz`.
4. Переменные окружения:

   | Переменная | Значение |
   |---|---|
   | `APP_ENV` | `production` |
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
   | `DATABASE_URL` | Internal Database URL из шага 1 |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | из Google Cloud Console |
   | `ADMIN_EMAILS` | ваш адрес Google |
   | `COOKIE_SECURE` | `true` |
   | `WEB_CONCURRENCY` | `1` (см. «Масштабирование») |

5. Запустите первый деплой — миграции применятся автоматически.

Демо-контент заливается **сам** при старте: `start.sh` вызывает
`python -m app.seed --bootstrap`, который наполняет каталог, только если он
пуст, и синхронизирует права админов из `ADMIN_EMAILS`. Ручной запуск и Shell
не нужны — это важно для бесплатных тарифов, где Shell недоступен.

`BASE_URL` можно не задавать: он выведется из `RENDER_EXTERNAL_URL`. Если
задаёте свой домен — укажите `BASE_URL=https://ваш-домен`.

## Почта (ответы поддержки)

Без настроенной почты вход по коду **не работает** — сайт честно сообщает об
этом, а не делает вид, что письмо отправлено.

> ⚠️ **Важно для бесплатного тарифа Render.** Бесплатные веб-сервисы Render
> **не могут** открывать исходящие SMTP-соединения: порты `25`, `465` и `587`
> закрыты платформой (это официальное ограничение free-плана). Поэтому
> **Gmail SMTP на бесплатном тарифе работать не будет** — соединение просто не
> установится. Используйте HTTP-API (см. ниже), он идёт по порту 443.

### Способ 1 — HTTP API (рекомендуется, работает на free-плане)

| Переменная | Значение |
|---|---|
| `EMAIL_API_PROVIDER` | `brevo` или `resend` |
| `EMAIL_API_KEY` | API-ключ из личного кабинета сервиса |

**Brevo** — бесплатно 300 писем в сутки. Достаточно подтвердить один адрес
отправителя (письмо с кодом уходит с вашего адреса, например
`ethernallhatred@gmail.com`):

1. Регистрация: <https://www.brevo.com>.
2. **Senders, Domains & Dedicated IPs** → **Senders** → добавьте свой адрес
   Gmail и подтвердите его по ссылке из письма.
3. **SMTP & API** → **API Keys** → **Generate a new API key**.
4. В Render → ваш сервис → **Environment** добавьте `EMAIL_API_PROVIDER=brevo`
   и `EMAIL_API_KEY=<ключ>`.

**Resend** работает так же (`EMAIL_API_PROVIDER=resend`), но без своего домена
письма уходят только на адрес владельца аккаунта — для теста годится, для
посетителей нет.

### Способ 2 — Gmail SMTP (только платный тариф Render)

На платном плане порты открыты, и можно использовать Gmail. Нужен **пароль
приложения** (16 символов), обычный пароль Google отклонит:

1. Включите двухэтапную аутентификацию: Google Account → **Security** →
   2-Step Verification.
2. Google Account → **Security** → **App passwords**
   (<https://myaccount.google.com/apppasswords>).
3. Создайте пароль и скопируйте его **без пробелов**.
4. Задайте `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=<адрес>`,
   `SMTP_PASSWORD=<пароль приложения>`.

### Проверка

Ответьте на любое обращение в дашборде (**Поддержка** → откройте тикет →
отправьте ответ). В логах Render должно появиться `EMAIL sent to=... via brevo`
(или `via resend`/`via smtp`). Если видите
`EMAIL not sent: no mail transport configured` — переменные не подхватились.
Если `EMAIL delivery failed` — неверный ключ или неподтверждённый отправитель.

> Вход по коду на почту **убран**: на free-плане Render отправка писем
> ненадёжна, поэтому основной вход — e-mail **или логин** и пароль, плюс
> Google и Telegram.

### Ограничения

- Бесплатные лимиты: Brevo — 300 писем/сутки, Resend — 100/сутки.
- Письма уходят с вашего личного адреса, пока не подтвердите собственный
  домен в сервисе. Для «фирменного» отправителя нужен домен.
- SMTP-транспорт оставлен в коде (`app/services/mailer.py`) для платных
  тарифов и локального запуска; при заданном `EMAIL_API_PROVIDER` он не
  используется.

## Масштабирование

По умолчанию сервис работает в **одном** процессе (`WEB_CONCURRENCY=1`), и это
намеренно. Состояние чата (`app/services/chat.py`) и счётчики rate-limit
(`app/security/ratelimit.py`) живут в памяти процесса. При нескольких воркерах
или инстансах:

- клиент и админ могут попасть в разные воркеры и **не увидят сообщения друг
  друга** в реальном времени;
- лимит запросов считается отдельно на каждый воркер, то есть фактический
  бюджет умножается на их число.

Чтобы масштабироваться, нужно сначала вынести это состояние в Redis
(например, `broadcast` через pub/sub, счётчики — через `INCR`/`EXPIRE`), и
только потом поднимать `WEB_CONCURRENCY` или `numInstances`.

### Подключения к БД

Пул ограничен (`DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`). Суммарное число
соединений = `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × число инстансов`. Держите его
ниже лимита вашего тарифа Postgres. `pool_pre_ping` и `DB_POOL_RECYCLE=1800`
нужны, потому что прокси Render закрывает простаивающие соединения.

## Тесты

```bash
pytest                       # весь набор
pytest tests/test_chat.py    # один модуль
pytest -q                    # краткий вывод
```

Каждый тест получает изолированную SQLite-базу (см. `tests/conftest.py`),
поэтому рабочая база не затрагивается. Покрыты вход и сессии, публичные
страницы, заказы и WebSocket-чат, дашборд, формат денег и ограничение
частоты запросов.

## Лицензия

© VA Digital Studio. Все права защищены.
