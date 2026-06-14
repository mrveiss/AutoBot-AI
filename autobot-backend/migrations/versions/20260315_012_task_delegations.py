# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create task_delegations table (#1753).

Revision ID: 20260315_012
Revises: 20260315_011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260315_012"
down_revision = "20260315_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_delegations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("delegator_id", sa.String(255), nullable=False),
        sa.Column("assignee_id", sa.String(255), nullable=False),
        sa.Column("task_description", sa.Text, nullable=False),
        sa.Column("context", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("escalated_to", sa.String(255), nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_task_delegations_delegator_id",
        "task_delegations",
        ["delegator_id"],
    )
    op.create_index(
        "ix_task_delegations_assignee_id",
        "task_delegations",
        ["assignee_id"],
    )
    op.create_index(
        "ix_task_delegations_status",
        "task_delegations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("task_delegations")
