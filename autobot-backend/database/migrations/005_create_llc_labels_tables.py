# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create llc_labels and llc_work_item_labels tables (GH#8254).

Revision ID: 005
Revises: 004
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llc_labels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("company_id", "name", name="uq_llc_labels_company_name"),
    )
    op.create_index("ix_llc_labels_company_id", "llc_labels", ["company_id"])

    op.create_table(
        "llc_work_item_labels",
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "label_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_labels.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("assigned_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("work_item_id", "label_id", name="uq_llc_work_item_labels"),
    )


def downgrade() -> None:
    op.drop_table("llc_work_item_labels")
    op.drop_index("ix_llc_labels_company_id", table_name="llc_labels")
    op.drop_table("llc_labels")
