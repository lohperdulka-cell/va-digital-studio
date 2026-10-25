"""Command line utilities.

Usage::

    python -m app.cli make_admin user@example.com
    python -m app.cli revoke_admin user@example.com
    python -m app.cli list_users
    python -m app.cli whoami user@example.com
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy import func, select

from app.config import settings
from app.database import session_scope
from app.logging_config import get_logger, setup_logging
from app.models import User

logger = get_logger("app.cli")


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or len(email) > 320:
        raise argparse.ArgumentTypeError(f"Некорректный e-mail: {value!r}")
    return email


def cmd_make_admin(email: str) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"✗ Пользователь {email} не найден.")
            print("  Пользователь появится в БД после первого входа через Google.")
            return 1
        if user.is_admin:
            print(f"• {user.email} уже администратор.")
            return 0
        user.is_admin = True
        logger.info("CLI granted admin to user_id=%s email=%s", user.id, user.email)
        print(f"✓ {user.email} назначен администратором.")
        return 0


def cmd_revoke_admin(email: str) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"✗ Пользователь {email} не найден.")
            return 1
        if not user.is_admin:
            print(f"• {user.email} не является администратором.")
            return 0
        if user.email in settings.admin_email_list:
            print(
                f"! Внимание: {user.email} входит в ADMIN_EMAILS, "
                "поэтому права вернутся при следующем входе."
            )
        user.is_admin = False
        logger.info("CLI revoked admin from user_id=%s", user.id)
        print(f"✓ Права администратора сняты с {user.email}.")
        return 0


def cmd_list_users() -> int:
    with session_scope() as db:
        users = db.scalars(select(User).order_by(User.id)).all()
        if not users:
            print("Пользователей пока нет.")
            return 0
        print(f"{'ID':>4}  {'ADMIN':<6} {'BALANCE':>10}  EMAIL")
        for user in users:
            flag = "да" if user.is_admin else "—"
            print(f"{user.id:>4}  {flag:<6} {user.balance:>10.2f}  {user.email}")
    return 0


def cmd_whoami(email: str) -> int:
    with session_scope() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"✗ Пользователь {email} не найден.")
            return 1
        print(
            f"id={user.id}\nemail={user.email}\nname={user.display_name}\n"
            f"admin={user.is_admin}\nbalance={user.balance}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Утилиты администрирования VA Digital Studio",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    make_admin = sub.add_parser("make_admin", help="выдать права администратора")
    make_admin.add_argument("email", type=_normalise_email)

    revoke = sub.add_parser("revoke_admin", help="снять права администратора")
    revoke.add_argument("email", type=_normalise_email)

    sub.add_parser("list_users", help="список пользователей")

    whoami = sub.add_parser("whoami", help="показать пользователя по e-mail")
    whoami.add_argument("email", type=_normalise_email)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)

    if args.command == "make_admin":
        return cmd_make_admin(args.email)
    if args.command == "revoke_admin":
        return cmd_revoke_admin(args.email)
    if args.command == "list_users":
        return cmd_list_users()
    if args.command == "whoami":
        return cmd_whoami(args.email)

    build_parser().print_help()  # pragma: no cover - argparse rejects first
    return 2


if __name__ == "__main__":
    sys.exit(main())
