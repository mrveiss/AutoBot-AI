# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create llc_work_item_attachments table (GH#8253).

Stores file attachment metadata for work items. File content is on disk
(local_disk) or an s3-compatible backend; only the storage_path is recorded
here. Text extraction status is tracked via text_extracted / extracted_text.

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
        "llc_work_item_attachments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("uploaded_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "text_extracted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_llc_work_item_attachments_work_item_id",
        "llc_work_item_attachments",
        ["work_item_id"],
    )
    op.create_index(
        "ix_llc_work_item_attachments_company_id",
        "llc_work_item_attachments",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llc_work_item_attachments_company_id", table_name="llc_work_item_attachments")
    op.drop_index("ix_llc_work_item_attachments_work_item_id", table_name="llc_work_item_attachments")
    op.drop_table("llc_work_item_attachments")
