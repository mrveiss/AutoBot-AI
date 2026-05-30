"""Add chat_shared_links table for public link sharing with optional password (GH#8996).

Revision ID: 20260531_049
Revises: 20260530_048
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260531_049"
down_revision: Union[str, None] = "20260530_048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_shared_links",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(128), nullable=False, index=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_chat_shared_links_session_id",
        "chat_shared_links",
        ["session_id"],
    )
    op.create_index(
        "ix_chat_shared_links_token",
        "chat_shared_links",
        ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_shared_links_token", table_name="chat_shared_links")
    op.drop_index("ix_chat_shared_links_session_id", table_name="chat_shared_links")
    op.drop_table("chat_shared_links")
