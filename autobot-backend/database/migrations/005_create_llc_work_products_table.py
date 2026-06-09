# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create llc_work_products table for artifact indexing into project KB (GH#8242).

Work products are the deliverables produced by agents when completing work items:
code, documents, reports, plans, screenshots, PR links, and other artifacts.
The ArtifactIngestor picks up rows where kb_indexed=false and indexes them into
the project ChromaDB collection for future RAG retrieval.

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


def _create_llc_work_products_table() -> None:
    op.create_table(
        "llc_work_products",
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
        sa.Column(
            "heartbeat_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "type",
            sa.String(32),
            nullable=False,
            comment="code|document|report|plan|screenshot|pr_link|other",
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column(
            "storage_path",
            sa.Text,
            nullable=True,
            comment="Path to binary/large file; text-only paths are also indexed",
        ),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column(
            "kb_indexed",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="True after ArtifactIngestor has indexed into project KB",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def _create_llc_work_products_indices() -> None:
    op.create_index("ix_llc_work_products_company_id", "llc_work_products", ["company_id"])
    op.create_index("ix_llc_work_products_work_item_id", "llc_work_products", ["work_item_id"])
    op.create_index("ix_llc_work_products_kb_indexed", "llc_work_products", ["kb_indexed"])
    op.create_index("ix_llc_work_products_created_at", "llc_work_products", ["created_at"])


def upgrade() -> None:
    _create_llc_work_products_table()
    _create_llc_work_products_indices()


def _drop_llc_work_products_indices() -> None:
    op.drop_index("ix_llc_work_products_created_at", table_name="llc_work_products")
    op.drop_index("ix_llc_work_products_kb_indexed", table_name="llc_work_products")
    op.drop_index("ix_llc_work_products_work_item_id", table_name="llc_work_products")
    op.drop_index("ix_llc_work_products_company_id", table_name="llc_work_products")


def downgrade() -> None:
    _drop_llc_work_products_indices()
    op.drop_table("llc_work_products")
