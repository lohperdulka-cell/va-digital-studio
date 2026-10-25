"""Authentication dependencies re-exported for routers.

``app.security.sessions`` holds the implementation; these aliases keep route
signatures short and make the intent obvious at the call site.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security.sessions import (
    get_current_admin,
    get_current_user,
    get_current_user_optional,
)

# Database session as a dependency.
DbSession = Annotated[Session, Depends(get_db)]

# Authenticated user; raises 401 (or redirects browsers) when absent.
CurrentUser = Annotated[User, Depends(get_current_user)]

# Authenticated administrator; raises 403 for a signed-in non-admin.
CurrentAdmin = Annotated[User, Depends(get_current_admin)]

# May be None for anonymous visitors.
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]

__all__ = [
    "CurrentAdmin",
    "CurrentUser",
    "DbSession",
    "OptionalUser",
    "get_current_admin",
    "get_current_user",
    "get_current_user_optional",
]
