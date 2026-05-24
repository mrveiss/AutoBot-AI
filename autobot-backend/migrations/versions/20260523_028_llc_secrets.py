# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC company-scoped secrets table (GH#8217).

Revision ID: 20260523_028
Revises: 20260523_027
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260523_028"
down_revision = "20260523_027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llc_secrets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("value", sa.LargeBinary, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by_agent_id", sa.String(255), nullable=False),
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_llc_secrets_company_name"),
    )
    op.create_index("ix_llc_secrets_company_id", "llc_secrets", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_secrets_company_id", table_name="llc_secrets")
    op.drop_table("llc_secrets")
