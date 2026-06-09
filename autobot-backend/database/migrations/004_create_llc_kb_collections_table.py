# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create llc_kb_collections table for KB lifecycle tracking (GH#8235).

Tracks all ChromaDB collections created for LLC entities with their
status (active/archived) and timestamps for audit compliance.

Revision ID: 004
Revises: 003
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def _create_llc_kb_collections_table() -> None:
    """Create llc_kb_collections table with all columns (GH#8235)."""
    op.create_table(
        "llc_kb_collections",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Collection identity
        sa.Column(
            "collection_name",
            sa.String(512),
            nullable=False,
            unique=True,
            comment="ChromaDB collection name (entity_type:entity_id[:suffix])",
        ),
        # Entity reference
        sa.Column(
            "entity_type",
            sa.String(50),
            nullable=False,
            comment="Type: company, project, sprint, work_item, agent",
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="ID of the entity that owns this collection",
        ),
        # Lifecycle status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="active or archived",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the collection was archived (null if active)",
        ),
    )


def _create_llc_kb_collections_indices() -> None:
    """Create indices for llc_kb_collections query performance (GH#8235)."""
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


def upgrade() -> None:
    """Create llc_kb_collections table with indices."""
    _create_llc_kb_collections_table()
    _create_llc_kb_collections_indices()


def _drop_llc_kb_collections_indices() -> None:
    """Drop indices from llc_kb_collections table (GH#8235)."""
    op.drop_index("ix_llc_kb_collections_created_at", table_name="llc_kb_collections")
    op.drop_index("ix_llc_kb_collections_status", table_name="llc_kb_collections")
    op.drop_index("ix_llc_kb_collections_entity", table_name="llc_kb_collections")


def downgrade() -> None:
    """Drop llc_kb_collections table."""
    _drop_llc_kb_collections_indices()
    op.drop_table("llc_kb_collections")
