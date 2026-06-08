# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add retention_policies table for data retention policy configuration (MVA-3145, GH#8995).

Revision ID: 20260604_051
Revises: 20260604_036
Create Date: 2026-06-04

Adds table for configurable data retention policies:
- Supports chat, file, audit, and knowledge base retention
- Global policies (user_id=NULL) and user-specific overrides
- Anonymization flag for GDPR compliance
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260604_051"
down_revision: Union[str, None] = "20260604_036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("policy_type", sa.String(50), nullable=False, index=True),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("anonymize_instead_of_delete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # Unique constraint: one policy per (policy_type, user_id)
    op.create_unique_constraint("uq_policy_type_user", "retention_policies", ["policy_type", "user_id"])

    # Composite index for efficient lookups
    op.create_index("idx_policy_type_user", "retention_policies", ["policy_type", "user_id"])


def downgrade() -> None:
    op.drop_index("idx_policy_type_user", table_name="retention_policies")
    op.drop_constraint("uq_policy_type_user", "retention_policies", type_="unique")
    op.drop_table("retention_policies")
