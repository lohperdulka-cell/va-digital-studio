"""drop the design category

Design work is no longer offered, so the studio's catalogue no longer has a
design bucket.  The column is a plain VARCHAR (the enum is not native), so the
only thing to clean up is the rows that still carry the old value: reading one
back into the narrowed Python enum would raise.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-26 23:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM services WHERE category = 'DESIGN'"))


def downgrade() -> None:
    # The rows are gone; there is nothing to restore.
    pass
