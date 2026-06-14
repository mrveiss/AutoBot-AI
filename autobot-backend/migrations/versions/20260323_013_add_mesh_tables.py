# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Create Neural Mesh RAG tables: mesh_nodes, mesh_edges, mesh_evolution_log (#2055).

Revision ID: 20260323_013
Revises: 20260315_012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260323_013"
down_revision = "20260315_012"
branch_labels = None
depends_on = None


def _create_mesh_nodes_table() -> None:
    """Create mesh_nodes table. Helper for upgrade() (#2055)."""
    op.create_table(
        "mesh_nodes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("chunk_id", sa.Text, nullable=False, unique=True),
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
    )
    op.create_index(
        "idx_mesh_nodes_anchor",
        "mesh_nodes",
        ["is_anchor"],
        postgresql_where=sa.text("is_anchor = TRUE"),
    )
    op.create_index("idx_mesh_nodes_type", "mesh_nodes", ["node_type"])


def _create_mesh_edges_table() -> None:
    """Create mesh_edges table. Helper for upgrade() (#2055)."""
    op.create_table(
        "mesh_edges",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "from_node",
            UUID(as_uuid=True),
            sa.ForeignKey("mesh_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "to_node",
            UUID(as_uuid=True),
            sa.ForeignKey("mesh_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("edge_type", sa.Text, nullable=False),
        sa.Column("weight", sa.Float, nullable=True, server_default="1.0"),
        sa.Column("origin", sa.Text, nullable=False, server_default="seeder"),
        sa.Column("co_access_count", sa.Integer, nullable=True, server_default="0"),
        sa.Column("last_reinforced", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("from_node", "to_node", "edge_type", name="uq_mesh_edges"),
    )
    _create_mesh_edges_indexes()


def _create_mesh_edges_indexes() -> None:
    """Create indexes for mesh_edges. Helper for _create_mesh_edges_table() (#2055)."""
    op.create_index(
        "idx_mesh_edges_weight",
        "mesh_edges",
        ["weight"],
        postgresql_where=sa.text("weight > 0.3"),
    )
    op.create_index("idx_mesh_edges_origin", "mesh_edges", ["origin"])
    op.create_index("idx_mesh_edges_from", "mesh_edges", ["from_node"])
    op.create_index("idx_mesh_edges_to", "mesh_edges", ["to_node"])


def _create_mesh_evolution_log_table() -> None:
    """Create mesh_evolution_log table. Helper for upgrade() (#2055)."""
    op.create_table(
        "mesh_evolution_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_mesh_evolution_type",
        "mesh_evolution_log",
        ["event_type", "created_at"],
    )


def upgrade() -> None:
    """Create mesh_nodes, mesh_edges, and mesh_evolution_log tables."""
    _create_mesh_nodes_table()
    _create_mesh_edges_table()
    _create_mesh_evolution_log_table()


def downgrade() -> None:
    """Drop mesh tables in dependency order."""
    op.drop_index("idx_mesh_evolution_type", table_name="mesh_evolution_log")
    op.drop_table("mesh_evolution_log")

    op.drop_index("idx_mesh_edges_to", table_name="mesh_edges")
    op.drop_index("idx_mesh_edges_from", table_name="mesh_edges")
    op.drop_index("idx_mesh_edges_origin", table_name="mesh_edges")
    op.drop_index("idx_mesh_edges_weight", table_name="mesh_edges")
    op.drop_table("mesh_edges")

    op.drop_index("idx_mesh_nodes_type", table_name="mesh_nodes")
    op.drop_index("idx_mesh_nodes_anchor", table_name="mesh_nodes")
    op.drop_table("mesh_nodes")
