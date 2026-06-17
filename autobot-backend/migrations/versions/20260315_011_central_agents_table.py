# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create central agents registry table (#1754).

Revision ID: 20260315_011
Revises: 20260315_010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260315_011"
down_revision = "20260315_010"
branch_labels = None
depends_on = None


def _add_timestamp_columns(table_name: str) -> None:
    """Add created_at / updated_at with server defaults."""
    op.add_column(
        table_name,
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        table_name,
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("agent_type", sa.String(50), nullable=False, server_default="worker"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    _add_timestamp_columns("agents")
    op.create_index("ix_agents_agent_id", "agents", ["agent_id"], unique=True)
    op.create_index("ix_agents_status", "agents", ["status"])


def downgrade() -> None:
    op.drop_table("agents")
