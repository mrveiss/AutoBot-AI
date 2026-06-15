# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Create llc_work_products + llc_work_item_relations (GH#10043).

These two wired ORM tables (``LLCWorkProduct``, ``LLCWorkItemRelation``) had no
creating migration — they were only ever built by the ``create_all`` bootstrap.
With the create_all faucet closed (#10001/#10026), a fresh ``alembic upgrade
head`` would have neither table, and ``work_product_service`` /
``work_item_relations`` / ``artifact_ingestor`` would 500 on first touch.

This migration creates both tables and their enum types with **lowercase enum
values** (matching the model's ``values_callable`` fix, #9980 — never the member
NAMES a bare ``sa.Enum(PyEnum)`` would emit). It is guarded with the #10027
helpers so it is a safe no-op on databases where ``create_all`` already built
the tables (the same situation migration 002 handles for ``secrets``).

Revision ID: 20260615_059
Revises: 20260614_058
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from migrations.guards import drop_pg_enum, ensure_pg_enum, has_table, pg_enum

revision = "20260615_059"
down_revision = "20260614_058"
branch_labels = None
depends_on = None

# Enum VALUES (lowercase) — must equal the model's values_callable output (#9980).
_workproducttype = pg_enum(
    "workproducttype",
    "code",
    "document",
    "report",
    "plan",
    "screenshot",
    "pr_link",
    "other",
)
_workitemrelationtype = pg_enum(
    "workitemrelationtype",
    "blocks",
    "blocked_by",
    "duplicates",
    "relates_to",
)


def upgrade() -> None:
    ensure_pg_enum(_workproducttype)
    ensure_pg_enum(_workitemrelationtype)

    if not has_table("llc_work_products"):
        op.create_table(
            "llc_work_products",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
            sa.Column("work_item_id", UUID(as_uuid=True), nullable=False),
            sa.Column("heartbeat_run_id", UUID(as_uuid=True), nullable=True),
            sa.Column("type", _workproducttype, nullable=False),
            sa.Column("title", sa.String(512), nullable=False),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("storage_path", sa.Text(), nullable=True),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("kb_indexed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["work_item_id"], ["llc_work_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["heartbeat_run_id"], ["llc_heartbeat_runs.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_llc_work_products_company_id", "llc_work_products", ["company_id"])
        op.create_index("ix_llc_work_products_work_item_id", "llc_work_products", ["work_item_id"])

    if not has_table("llc_work_item_relations"):
        op.create_table(
            "llc_work_item_relations",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
            sa.Column("source_id", UUID(as_uuid=True), nullable=False),
            sa.Column("target_id", UUID(as_uuid=True), nullable=False),
            sa.Column("relation_type", _workitemrelationtype, nullable=False),
            sa.Column("created_by_agent_id", UUID(as_uuid=True), nullable=True),
            sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(["source_id"], ["llc_work_items.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["target_id"], ["llc_work_items.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("source_id", "target_id", "relation_type", name="uq_work_item_relation"),
            sa.CheckConstraint("source_id != target_id", name="ck_work_item_relation_no_self"),
        )
        op.create_index("ix_llc_work_item_relations_company_id", "llc_work_item_relations", ["company_id"])
        op.create_index("ix_llc_work_item_relations_source_id", "llc_work_item_relations", ["source_id"])
        op.create_index("ix_llc_work_item_relations_target_id", "llc_work_item_relations", ["target_id"])


def downgrade() -> None:
    op.drop_table("llc_work_item_relations")
    op.drop_table("llc_work_products")
    drop_pg_enum(_workitemrelationtype)
    drop_pg_enum(_workproducttype)
