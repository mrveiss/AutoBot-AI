# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add LLC extension columns to organizations table.

Revision ID: 20260523_023
Revises: 20260523_022
Create Date: 2026-05-23 00:00:00.000000

GH#8211: Extends the organizations table with sub-company hierarchy, budget
tracking, per-company issue numbering, brand settings, and LLC lifecycle
status columns needed by the LLC module.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_023"
down_revision: Union[str, None] = "20260523_022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sub-company hierarchy
    op.add_column(
        "organizations",
        sa.Column(
            "parent_org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_organizations_parent_org_id", "organizations", ["parent_org_id"])

    # Per-company issue numbering
    op.add_column(
        "organizations",
        sa.Column("issue_prefix", sa.Text(), nullable=True),
    )
    op.create_index("ix_organizations_issue_prefix", "organizations", ["issue_prefix"], unique=True)
    op.add_column(
        "organizations",
        sa.Column("issue_counter", sa.Integer(), nullable=False, server_default="0"),
    )

    # Budget tracking (cents to avoid float precision issues)
    op.add_column(
        "organizations",
        sa.Column("budget_monthly_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "organizations",
        sa.Column("spent_monthly_cents", sa.Integer(), nullable=False, server_default="0"),
    )

    # Branding
    op.add_column(
        "organizations",
        sa.Column("brand_color", sa.Text(), nullable=True),
    )

    # Governance
    op.add_column(
        "organizations",
        sa.Column(
            "require_approval_for_hires",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # LLC lifecycle status
    op.add_column(
        "organizations",
        sa.Column("llc_status", sa.String(32), nullable=False, server_default="onboarding"),
    )
    op.add_column(
        "organizations",
        sa.Column("pause_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "paused_at")
    op.drop_column("organizations", "pause_reason")
    op.drop_column("organizations", "llc_status")
    op.drop_column("organizations", "require_approval_for_hires")
    op.drop_column("organizations", "brand_color")
    op.drop_column("organizations", "spent_monthly_cents")
    op.drop_column("organizations", "budget_monthly_cents")
    op.drop_column("organizations", "issue_counter")
    op.drop_index("ix_organizations_issue_prefix", table_name="organizations")
    op.drop_column("organizations", "issue_prefix")
    op.drop_index("ix_organizations_parent_org_id", table_name="organizations")
    op.drop_column("organizations", "parent_org_id")
