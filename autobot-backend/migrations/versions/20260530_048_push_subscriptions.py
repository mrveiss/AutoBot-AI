# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add push_subscriptions table for web push notification delivery (GH#4459).

Revision ID: 20260530_048
Revises: 20260529_047
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260530_048"
down_revision: Union[str, None] = "20260529_047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Index("ix_push_subscriptions_user_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
