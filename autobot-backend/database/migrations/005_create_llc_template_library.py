# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Create llc_template_library and llc_template_tags tables (GH#8260).

Platform-level template index for cross-company template discovery, search,
and import. Templates are ChromaDB-indexed for semantic search.

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

_TEMPLATE_CATEGORY_ENUM = postgresql.ENUM(
    "company",
    "project",
    "agent_role",
    "workflow",
    name="llc_template_category",
)


def _create_llc_template_library_table() -> None:
    """Create llc_template_library table (GH#8260)."""
    op.create_table(
        "llc_template_library",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
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
            postgresql.JSONB,
            nullable=False,
            comment="Scrubbed export JSON — no raw secrets",
        ),
        sa.Column(
            "created_by_company_id",
            postgresql.UUID(as_uuid=True),
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
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Provenance: set when this template was imported from another template",
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
            onupdate=sa.func.now(),
        ),
    )


def _create_llc_template_tags_table() -> None:
    """Create llc_template_tags join table (GH#8260)."""
    op.create_table(
        "llc_template_tags",
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
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


def _create_indices() -> None:
    """Create query-performance indices for template tables (GH#8260)."""
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
    op.create_index(
        "ix_llc_template_tags_tag",
        "llc_template_tags",
        ["tag"],
    )


def upgrade() -> None:
    """Create template library tables with indices."""
    _create_llc_template_library_table()
    _create_llc_template_tags_table()
    _create_indices()


def _drop_indices() -> None:
    """Drop template library indices (GH#8260)."""
    op.drop_index("ix_llc_template_tags_tag", table_name="llc_template_tags")
    op.drop_index("ix_llc_template_library_created_at", table_name="llc_template_library")
    op.drop_index("ix_llc_template_library_created_by", table_name="llc_template_library")
    op.drop_index("ix_llc_template_library_is_public", table_name="llc_template_library")
    op.drop_index("ix_llc_template_library_category", table_name="llc_template_library")


def downgrade() -> None:
    """Drop template library tables."""
    _drop_indices()
    op.drop_table("llc_template_tags")
    op.drop_table("llc_template_library")
