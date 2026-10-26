"""Password hashing and password policy.

Uses the ``bcrypt`` library directly rather than ``passlib``: passlib 1.7.4
crashes against bcrypt 5.x (it reads a ``bcrypt.__about__`` attribute that was
removed), and pinning an old bcrypt to keep passlib alive is a worse trade than
dropping the thin wrapper.
"""

from __future__ import annotations

import hmac
import re

import bcrypt

from app.config import settings

# bcrypt hashes at most 72 bytes and raises on anything longer.
_MAX_BYTES = 72

# Deliberately not exotic: the goal is to block the passwords that appear at
# the top of every breach list, not to police how people write a passphrase.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "qwertyuiop",
        "iloveyou",
        "admin123",
        "administrator",
        "letmein",
        "welcome",
        "welcome1",
        "monkey123",
        "football",
        "baseball",
        "dragon123",
        "sunshine",
        "princess",
        "superman",
        "trustno1",
        "passw0rd",
        "p@ssw0rd",
        "йцукен",
        "пароль",
        "пароль123",
        "qazwsx123",
    }
)


class PasswordPolicyError(ValueError):
    """Raised when a password fails the policy; the message is user-facing."""


def _to_bytes(password: str) -> bytes:
    """Encode and truncate to bcrypt's 72-byte limit.

    Truncating rather than rejecting keeps very long passphrases usable; the
    cut happens on the UTF-8 byte string, so it can never split a character
    into invalid input for bcrypt.
    """
    return password.encode("utf-8")[:_MAX_BYTES]


def hash_password(password: str) -> str:
    """Return a bcrypt hash (cost 12) for ``password``."""
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time check of ``password`` against a stored hash.

    Returns ``False`` for an empty hash so an account with no password set
    cannot be entered by submitting an empty one.
    """
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # Malformed hash in the database — treat as a failed login, not a 500.
        return False


def validate_password(password: str, *, email: str = "") -> None:
    """Raise :class:`PasswordPolicyError` if the password is unacceptable."""
    minimum = max(8, settings.password_min_length)

    if len(password) < minimum:
        raise PasswordPolicyError(f"Пароль должен быть не короче {minimum} символов")
    if len(password) > 200:
        raise PasswordPolicyError("Пароль слишком длинный (максимум 200 символов)")
    if password.lower() in _COMMON_PASSWORDS:
        raise PasswordPolicyError("Этот пароль слишком простой — выберите другой")
    if password.isdigit() or password.isalpha():
        raise PasswordPolicyError(
            "Пароль должен содержать и буквы, и цифры или символы"
        )
    if not re.search(r"[A-Za-zА-Яа-я]", password) or not re.search(r"\d|\W", password):
        raise PasswordPolicyError(
            "Пароль должен содержать и буквы, и цифры или символы"
        )

    # Reject a password built from the address itself ("ivan" in "ivan123").
    # Split on the usual separators so "ivan.petrov@..." also protects "ivan".
    local_part = email.split("@", 1)[0].strip().lower() if email else ""
    fragments = {local_part, *re.split(r"[^a-zа-я0-9]+", local_part)}
    lowered = password.lower()
    for fragment in fragments:
        if len(fragment) >= 4 and fragment in lowered:
            raise PasswordPolicyError("Пароль не должен содержать ваш e-mail")


def passwords_match(first: str, second: str) -> bool:
    """Constant-time comparison of two submitted passwords."""
    return hmac.compare_digest(first.encode("utf-8"), second.encode("utf-8"))
