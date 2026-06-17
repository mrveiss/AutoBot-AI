# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add config_revisions table for audit trail and rollback

Revision ID: 20260315_008
Revises: 20260309_007
Create Date: 2026-03-15 00:00:00.000000

Issue #1404: Config audit trail with versioning and rollback
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260315_008"
down_revision = "20260309_007"
branch_labels = None
depends_on = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_UUID = postgresql.UUID(as_uuid=True)


def _common_ts_cols():
    """Return created_at/updated_at Column defs. Helper (#1404)."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Create config_revisions table."""
    op.create_table(
        "config_revisions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("before_config", _JSONB, nullable=True),
        sa.Column("after_config", _JSONB, nullable=False),
        sa.Column("changed_keys", _JSONB, nullable=False, server_default="[]"),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        *_common_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_config_revisions_entity_type",
        "config_revisions",
        ["entity_type"],
    )
    op.create_index(
        "ix_config_revisions_entity_id",
        "config_revisions",
        ["entity_id"],
    )
    op.create_index(
        "ix_config_revisions_source",
        "config_revisions",
        ["source"],
    )
    op.create_index(
        "ix_config_revisions_created_by",
        "config_revisions",
        ["created_by"],
    )
    # Composite index for the primary query pattern: list by entity
    op.create_index(
        "ix_config_revisions_entity_type_entity_id",
        "config_revisions",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    """Drop config_revisions table."""
    for idx in [
        "ix_config_revisions_entity_type_entity_id",
        "ix_config_revisions_created_by",
        "ix_config_revisions_source",
        "ix_config_revisions_entity_id",
        "ix_config_revisions_entity_type",
    ]:
        op.drop_index(idx, table_name="config_revisions")
    op.drop_table("config_revisions")
