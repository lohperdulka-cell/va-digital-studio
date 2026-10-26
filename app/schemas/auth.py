"""Validation schemas for the sign-in forms.

Forms arrive as raw strings, so each model normalises before use: e-mail is
lower-cased and length-bounded, the password policy runs here (so a bad
password is rejected before it reaches the hasher), and every free-text field
is stripped.  Pydantic's ``EmailStr`` rejects malformed addresses outright,
which is the first line of defence against junk reaching the database.
"""

from __future__ import annotations

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.security.passwords import (
    PasswordPolicyError,
    passwords_match,
    validate_password,
)
from app.security.tokens import safe_next_path

# A six-digit code; the field is kept as a string so leading zeros survive.
_CODE_RE = re.compile(r"^\d{6}$")

_NAME_MAX = 200
_EMAIL_MAX = 320
_PASSWORD_MAX = 200


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


def _lowercase_email(value: str) -> str:
    """Lower-case and trim an address before anything else uses it."""
    return value.strip().lower()


class LoginForm(_Base):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)
    next: str = ""

    _normalise_email = field_validator("email")(_lowercase_email)

    @field_validator("next")
    @classmethod
    def _safe_next(cls, value: str) -> str:
        # Never trust a submitted redirect target.
        return safe_next_path(value, default="")


class RegisterForm(_Base):
    email: EmailStr
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)
    password_confirm: str = Field(min_length=1, max_length=_PASSWORD_MAX)
    name: str = Field(default="", max_length=_NAME_MAX)

    _normalise_email = field_validator("email")(_lowercase_email)

    @field_validator("password")
    @classmethod
    def _policy(cls, value: str) -> str:
        try:
            validate_password(value)
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("password_confirm")
    @classmethod
    def _same(cls, value: str, info) -> str:
        password = info.data.get("password")
        if password and not passwords_match(password, value):
            raise ValueError("Пароли не совпадают")
        return value

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        # Collapse whitespace; names are rendered, never used in a query.
        return " ".join(value.split())

    @model_validator(mode="after")
    def _password_not_from_email(self) -> RegisterForm:
        """Re-run the policy with the address known, to catch 'ivan' in 'ivan123'."""
        try:
            validate_password(self.password, email=str(self.email))
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CodeRequestForm(_Base):
    email: EmailStr

    _normalise_email = field_validator("email")(_lowercase_email)


class CodeVerifyForm(_Base):
    email: EmailStr
    # Length is enforced by the validator below so a short code gets the
    # Russian "6 digits" message instead of a raw pydantic length error.
    code: str = Field(min_length=1, max_length=20)

    _normalise_email = field_validator("email")(_lowercase_email)

    @field_validator("code")
    @classmethod
    def _six_digits(cls, value: str) -> str:
        cleaned = value.strip().replace(" ", "")
        if not _CODE_RE.match(cleaned):
            raise ValueError("Код состоит из 6 цифр")
        return cleaned


class TelegramStartForm(_Base):
    email: EmailStr

    _normalise_email = field_validator("email")(_lowercase_email)


