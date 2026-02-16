# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add hierarchical access levels to secrets

Revision ID: 002
Revises: 001
Create Date: 2026-02-16

Issue #685: Add org_id and team_ids for hierarchical secret access
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add org_id and team_ids columns to secrets table for hierarchical access."""
    # Add org_id column
    op.add_column(
        "secrets",
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Organization ID for org-level secrets (Issue #685)",
        ),
    )

    # Add index on org_id
    op.create_index(
        "ix_secrets_org_id",
        "secrets",
        ["org_id"],
    )

    # Add team_ids column
    op.add_column(
        "secrets",
        sa.Column(
            "team_ids",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="Array of team IDs for group-scoped secrets (Issue #685)",
        ),
    )

    # Update scope column comment to reflect new options
    op.alter_column(
        "secrets",
        "scope",
        comment="Visibility scope: user, session, shared, group, or organization",
    )


def downgrade() -> None:
    """Remove org_id and team_ids columns from secrets table."""
    # Remove team_ids column
    op.drop_column("secrets", "team_ids")

    # Remove org_id index and column
    op.drop_index("ix_secrets_org_id", table_name="secrets")
    op.drop_column("secrets", "org_id")

    # Restore original scope comment
    op.alter_column(
        "secrets",
        "scope",
        comment="Visibility scope: user, session, or shared",
    )
