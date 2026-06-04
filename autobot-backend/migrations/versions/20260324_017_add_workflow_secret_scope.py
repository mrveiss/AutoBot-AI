# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add workflow scope support to secrets table.

Adds a nullable ``workflow_id`` column to the ``secrets`` table so that secrets
can be scoped to a specific workflow in addition to user/session/shared/group/
organization scopes.  Also updates the ``scope`` column comment to document the
new ``workflow`` scope value.

Revision ID: 20260324_017
Revises: 20260324_016
Issue #2153 — Secret management for workflow credentials.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260324_017"
down_revision: str | None = "20260324_016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add workflow_id column and workflow index to secrets table. Issue #2153."""
    op.add_column(
        "secrets",
        sa.Column(
            "workflow_id",
            sa.String(128),
            nullable=True,
            comment=("Workflow ID for workflow-scoped secrets (Issue #2153). " "Set when scope='workflow'."),
        ),
    )

    op.create_index(
        "ix_secrets_workflow_id",
        "secrets",
        ["workflow_id"],
    )

    op.alter_column(
        "secrets",
        "scope",
        comment=("Visibility scope: user, session, shared, group, organization, or workflow"),
    )


def downgrade() -> None:
    """Remove workflow_id column and index from secrets table. Issue #2153."""
    op.drop_index("ix_secrets_workflow_id", table_name="secrets")
    op.drop_column("secrets", "workflow_id")

    op.alter_column(
        "secrets",
        "scope",
        comment=("Visibility scope: user, session, shared, group, or organization"),
    )
