# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create 8 LLC feature tables missing from the live DB (#10750 A2).

The following tables are declared in ORM models (and/or raw-SQL services) but
were never reachable via the canonical Alembic chain — they only existed in the
orphaned ``database/migrations/`` chain which was never applied:

  llc_labels                 — per-company label definitions
  llc_work_item_labels       — M:N join: work items ↔ labels
  llc_work_item_attachments  — file attachment metadata for work items
  llc_ceo_chat_threads       — one CEO Chat thread per decision/conversation
  llc_ceo_chat_messages      — ordered messages within a CEO Chat thread
  llc_template_library       — platform-level template index
  llc_template_tags          — join: templates ↔ tags
  llc_kb_collections         — ChromaDB collection lifecycle registry

Without these tables every request that touches labels, attachments, CEO-chat,
custom templates, or the KB-collection registry raises
``UndefinedTableError`` (500 on those endpoints).

Source of truth for columns/types/FKs/indexes:
  - ORM models in ``llc/models/`` (label, attachment, ceo_chat)
  - Raw-SQL service code (template.py) + orphaned DDL (005_create_llc_template_library.py)
  - Orphaned DDL (004_create_llc_kb_collections_table.py) for llc_kb_collections

``user_management.models.base.Base`` adds implicit ``created_at``/``updated_at``
to every ORM model.  Tables whose models do NOT explicitly re-declare
``updated_at`` still have the column (from Base) — migration 063 already
adds it to existing tables via ``ADD COLUMN IF NOT EXISTS``; this migration
creates the new tables with the column included from the start to keep the
ORM fully satisfied.

Idempotent: every ``op.create_table`` is guarded by ``has_table``.
No PostgreSQL ENUM types are needed (all status/category columns use VARCHAR).

Revision ID: 20260630_065
Revises: 20260630_064
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.guards import has_table

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "20260630_065"
down_revision: Union[str, None] = "20260630_064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. llc_labels
    #    Source: llc/models/label.py :: LLCLabel
    #    Columns: id, company_id, name, color, description,
    #             created_at (explicit override of Base),
    #             created_by,
    #             updated_at (from Base — not explicitly in model but ORM maps it)
    #    Constraints: PK(id), UQ(company_id, name)
    #    Indexes: ix_llc_labels_company_id
    #    Note: orphaned 005_create_llc_labels_tables.py omits updated_at;
    #          we add it here so migration 063 ADD COLUMN IF NOT EXISTS is a no-op.
    # ------------------------------------------------------------------
    if not has_table("llc_labels"):
        op.create_table(
            "llc_labels",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
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
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("company_id", "name", name="uq_llc_labels_company_name"),
        )
        op.create_index("ix_llc_labels_company_id", "llc_labels", ["company_id"])

    # ------------------------------------------------------------------
    # 2. llc_work_item_labels
    #    Source: llc/models/label.py :: LLCWorkItemLabel
    #    Columns: work_item_id, label_id, assigned_at, assigned_by
    #             created_at, updated_at (from Base)
    #    Constraints: PK(work_item_id, label_id), UQ(work_item_id, label_id)
    #                 FK work_item_id → llc_work_items.id CASCADE
    #                 FK label_id → llc_labels.id CASCADE
    #    Note: the model's PK is composite (work_item_id, label_id) which
    #          makes the UQ redundant but we declare it to match the ORM.
    # ------------------------------------------------------------------
    if not has_table("llc_work_item_labels"):
        op.create_table(
            "llc_work_item_labels",
            sa.Column(
                "work_item_id",
                UUID(as_uuid=True),
                sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "label_id",
                UUID(as_uuid=True),
                sa.ForeignKey("llc_labels.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "assigned_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("assigned_by", sa.String(255), nullable=True),
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
            sa.UniqueConstraint("work_item_id", "label_id", name="uq_llc_work_item_labels"),
        )

    # ------------------------------------------------------------------
    # 3. llc_work_item_attachments
    #    Source: llc/models/attachment.py :: LLCWorkItemAttachment
    #    Columns: id, company_id, work_item_id, uploaded_by_agent_id,
    #             uploaded_by_user_id, filename, content_type, size_bytes,
    #             storage_path, text_extracted, extracted_text,
    #             created_at (explicit override),
    #             updated_at (from Base)
    #    Indexes: ix_llc_work_item_attachments_company_id,
    #             ix_llc_work_item_attachments_work_item_id
    # ------------------------------------------------------------------
    if not has_table("llc_work_item_attachments"):
        op.create_table(
            "llc_work_item_attachments",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
            sa.Column(
                "work_item_id",
                UUID(as_uuid=True),
                sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("uploaded_by_agent_id", UUID(as_uuid=True), nullable=True),
            sa.Column("uploaded_by_user_id", UUID(as_uuid=True), nullable=True),
            sa.Column("filename", sa.Text, nullable=False),
            sa.Column("content_type", sa.Text, nullable=False),
            sa.Column("size_bytes", sa.Integer, nullable=False),
            sa.Column("storage_path", sa.Text, nullable=False),
            sa.Column(
                "text_extracted",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("extracted_text", sa.Text, nullable=True),
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
        op.create_index(
            "ix_llc_work_item_attachments_company_id",
            "llc_work_item_attachments",
            ["company_id"],
        )
        op.create_index(
            "ix_llc_work_item_attachments_work_item_id",
            "llc_work_item_attachments",
            ["work_item_id"],
        )

    # ------------------------------------------------------------------
    # 4. llc_ceo_chat_threads
    #    Source: llc/models/ceo_chat.py :: LLCCeoChatThread
    #    Columns: id, company_id, title, resolved_entity_type,
    #             resolved_entity_id, created_by_user_id, created_at, updated_at
    #    Indexes: ix_llc_ceo_chat_threads_company_id,
    #             ix_llc_ceo_chat_threads_created_by_user_id
    #    FK: created_by_user_id → users.id SET NULL
    # ------------------------------------------------------------------
    if not has_table("llc_ceo_chat_threads"):
        op.create_table(
            "llc_ceo_chat_threads",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("company_id", UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.Text, nullable=False),
            sa.Column("resolved_entity_type", sa.Text, nullable=True),
            sa.Column("resolved_entity_id", UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_by_user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
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
        )
        op.create_index(
            "ix_llc_ceo_chat_threads_company_id",
            "llc_ceo_chat_threads",
            ["company_id"],
        )
        op.create_index(
            "ix_llc_ceo_chat_threads_created_by_user_id",
            "llc_ceo_chat_threads",
            ["created_by_user_id"],
        )

    # ------------------------------------------------------------------
    # 5. llc_ceo_chat_messages
    #    Source: llc/models/ceo_chat.py :: LLCCeoChatMessage
    #    Columns: id, thread_id, author_type, author_user_id, body,
    #             created_at (explicit override),
    #             updated_at (from Base)
    #    FK: thread_id → llc_ceo_chat_threads.id CASCADE
    #        author_user_id → users.id SET NULL
    #    Indexes: ix_llc_ceo_chat_messages_thread_id
    # ------------------------------------------------------------------
    if not has_table("llc_ceo_chat_messages"):
        op.create_table(
            "llc_ceo_chat_messages",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "thread_id",
                UUID(as_uuid=True),
                sa.ForeignKey("llc_ceo_chat_threads.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("author_type", sa.String(16), nullable=False),
            sa.Column(
                "author_user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("body", sa.Text, nullable=False),
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
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_llc_ceo_chat_messages_thread_id",
            "llc_ceo_chat_messages",
            ["thread_id"],
        )

    # ------------------------------------------------------------------
    # 6. llc_template_library
    #    Source: orphaned 005_create_llc_template_library.py + services/template.py
    #    No SQLAlchemy ORM model exists — service uses raw SQL exclusively.
    #    Columns match the SQL INSERT/SELECT in template.py:
    #      id, name, description, category, template_json,
    #      created_by_company_id, is_public, usage_count,
    #      source_template_id, created_at, updated_at
    #    Indexes: ix_llc_template_library_category,
    #             ix_llc_template_library_is_public,
    #             ix_llc_template_library_created_by,
    #             ix_llc_template_library_created_at
    # ------------------------------------------------------------------
    if not has_table("llc_template_library"):
        op.create_table(
            "llc_template_library",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column(
                "category",
                sa.String(50),
                nullable=False,
                comment="company | project | agent_role | workflow",
            ),
            sa.Column(
                "template_json",
                JSONB,
                nullable=False,
                comment="Scrubbed export JSON — no raw secrets",
            ),
            sa.Column(
                "created_by_company_id",
                UUID(as_uuid=True),
                nullable=True,
                comment="Owning company; null for platform-seeded templates",
            ),
            sa.Column(
                "is_public",
                sa.Boolean,
                nullable=False,
                server_default="false",
                comment="Public templates visible to all companies",
            ),
            sa.Column(
                "usage_count",
                sa.Integer,
                nullable=False,
                server_default="0",
                comment="Incremented on each successful import",
            ),
            sa.Column(
                "source_template_id",
                UUID(as_uuid=True),
                nullable=True,
                comment="Provenance: set when imported from another template",
            ),
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
        op.create_index(
            "ix_llc_template_library_category",
            "llc_template_library",
            ["category"],
        )
        op.create_index(
            "ix_llc_template_library_is_public",
            "llc_template_library",
            ["is_public"],
        )
        op.create_index(
            "ix_llc_template_library_created_by",
            "llc_template_library",
            ["created_by_company_id"],
        )
        op.create_index(
            "ix_llc_template_library_created_at",
            "llc_template_library",
            ["created_at"],
        )

    # ------------------------------------------------------------------
    # 7. llc_template_tags
    #    Source: orphaned 005_create_llc_template_library.py + _upsert_tags() in template.py
    #    No ORM model — service uses raw SQL.
    #    Columns: template_id (PK+FK), tag (PK)
    #    FK: template_id → llc_template_library.id CASCADE
    #    Index: ix_llc_template_tags_tag
    # ------------------------------------------------------------------
    if not has_table("llc_template_tags"):
        op.create_table(
            "llc_template_tags",
            sa.Column(
                "template_id",
                UUID(as_uuid=True),
                sa.ForeignKey("llc_template_library.id", ondelete="CASCADE"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "tag",
                sa.String(100),
                primary_key=True,
                nullable=False,
            ),
        )
        op.create_index(
            "ix_llc_template_tags_tag",
            "llc_template_tags",
            ["tag"],
        )

    # ------------------------------------------------------------------
    # 8. llc_kb_collections
    #    Source: orphaned 004_create_llc_kb_collections_table.py
    #    No ORM model — KbCollectionManager uses ChromaDB directly;
    #    this table is the Postgres-side lifecycle registry.
    #    Columns: id, collection_name (UNIQUE), entity_type, entity_id,
    #             status, created_at, archived_at
    #    Indexes: ix_llc_kb_collections_entity (entity_type, entity_id),
    #             ix_llc_kb_collections_status,
    #             ix_llc_kb_collections_created_at
    # ------------------------------------------------------------------
    if not has_table("llc_kb_collections"):
        op.create_table(
            "llc_kb_collections",
            sa.Column(
                "id",
                UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "collection_name",
                sa.String(512),
                nullable=False,
                unique=True,
                comment="ChromaDB collection name (entity_type:entity_id[:suffix])",
            ),
            sa.Column(
                "entity_type",
                sa.String(50),
                nullable=False,
                comment="Type: company, project, sprint, work_item, agent",
            ),
            sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="active",
                comment="active or archived",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_llc_kb_collections_entity",
            "llc_kb_collections",
            ["entity_type", "entity_id"],
        )
        op.create_index(
            "ix_llc_kb_collections_status",
            "llc_kb_collections",
            ["status"],
        )
        op.create_index(
            "ix_llc_kb_collections_created_at",
            "llc_kb_collections",
            ["created_at"],
        )


# ---------------------------------------------------------------------------
# downgrade — forward-only, consistent with 063/064
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Forward-only: dropping these tables re-breaks every endpoint that
    # touches labels, attachments, CEO-chat, templates, and KB collections.
    # Consistent with the forward-only approach used in 063 and 064.
    pass
