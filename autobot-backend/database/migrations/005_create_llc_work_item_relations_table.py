# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Migration: create llc_work_item_relations table (GH#8252)."""

import sqlalchemy as sa
from sqlalchemy import text


def upgrade(op) -> None:
    op.execute(text("CREATE TYPE workitemrelationtype AS ENUM " "('blocks', 'blocked_by', 'duplicates', 'relates_to')"))

    op.create_table(
        "llc_work_item_relations",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relation_type",
            sa.Enum(
                "blocks",
                "blocked_by",
                "duplicates",
                "relates_to",
                name="workitemrelationtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("created_by_agent_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=text("now()"),
        ),
        sa.UniqueConstraint("source_id", "target_id", "relation_type", name="uq_work_item_relation"),
        sa.CheckConstraint("source_id != target_id", name="ck_work_item_relation_no_self"),
    )

    op.create_index("ix_llc_work_item_relations_company_id", "llc_work_item_relations", ["company_id"])
    op.create_index("ix_llc_work_item_relations_source_id", "llc_work_item_relations", ["source_id"])
    op.create_index("ix_llc_work_item_relations_target_id", "llc_work_item_relations", ["target_id"])


def downgrade(op) -> None:
    op.drop_table("llc_work_item_relations")
    op.execute(text("DROP TYPE IF EXISTS workitemrelationtype"))
