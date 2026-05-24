# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC per-agent budget table (GH#8215).

Revision ID: 20260523_025
Revises: 20260523_024
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa

revision = "20260523_025"
down_revision = "20260523_024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llc_agent_budgets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False, unique=True),
        sa.Column("budget_limit", sa.Numeric(15, 6), nullable=False),
        sa.Column("budget_spent", sa.Numeric(15, 6), nullable=False, server_default="0"),
        sa.Column("alert_threshold", sa.Float, nullable=False, server_default="0.8"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_agent_budgets_company_id", "llc_agent_budgets", ["company_id"])
    op.create_index("ix_llc_agent_budgets_agent_id", "llc_agent_budgets", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_agent_budgets_agent_id", table_name="llc_agent_budgets")
    op.drop_index("ix_llc_agent_budgets_company_id", table_name="llc_agent_budgets")
    op.drop_table("llc_agent_budgets")
