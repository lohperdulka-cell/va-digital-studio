"""link support tickets to orders

A finished order's chat is read-only, so the owner reaches the studio through
the support form instead.  The ticket remembers which order it came from, and
that link is what lets staff reopen the order's chat under the "Поддержка"
status.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-27 09:40:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("support_tickets") as batch:
        batch.add_column(
            sa.Column("order_id", sa.Integer(), nullable=True)
        )
        batch.create_foreign_key(
            "fk_support_tickets_order_id_orders",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_support_tickets_order_id", ["order_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("support_tickets") as batch:
        batch.drop_index("ix_support_tickets_order_id")
        batch.drop_constraint(
            "fk_support_tickets_order_id_orders", type_="foreignkey"
        )
        batch.drop_column("order_id")
