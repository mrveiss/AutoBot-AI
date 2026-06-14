# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create mesh_nodes_archive table for orphan-node archival (#2212).

MeshDB.archive_orphan_nodes() inserts into mesh_nodes_archive, but no
migration previously created this table.  The schema mirrors mesh_nodes
with one addition: an ``archived_at`` timestamp.

Revision ID: 20260324_015
Revises: 20260323_014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260324_015"
down_revision = "20260323_014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mesh_nodes_archive table mirroring mesh_nodes (#2212)."""
    op.create_table(
        "mesh_nodes_archive",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_id", sa.Text, nullable=False),
        sa.Column("source_file", sa.Text, nullable=True),
        sa.Column("node_type", sa.Text, nullable=False, server_default="doc"),
        sa.Column("raptor_level", sa.Integer, nullable=True, server_default="0"),
        sa.Column("access_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("is_anchor", sa.Boolean, nullable=True, server_default="false"),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_mesh_nodes_archive_at",
        "mesh_nodes_archive",
        ["archived_at"],
    )


def downgrade() -> None:
    """Drop mesh_nodes_archive table (#2212)."""
    op.drop_index("idx_mesh_nodes_archive_at", table_name="mesh_nodes_archive")
    op.drop_table("mesh_nodes_archive")
