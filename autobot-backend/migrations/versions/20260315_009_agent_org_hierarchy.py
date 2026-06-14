# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add agent org hierarchy: agent_org_nodes table with reporting lines

Revision ID: 20260315_009
Revises: 20260315_008
Create Date: 2026-03-15 00:00:00.000000

Issue #1405: Agent org charts with role hierarchy and reporting lines.

No existing SQL 'agents' table exists in the schema — agents are identified
by string IDs across the codebase. This migration creates agent_org_nodes,
which stores org-hierarchy metadata keyed by agent_id (String), matching
the convention used in agent_runtime_state and heartbeat_runs.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260315_009"
down_revision = "20260315_008"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)


def _common_ts_cols():
    """Return created_at/updated_at Column defs. Helper (#1405)."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Create agent_org_nodes table for org hierarchy (#1405)."""
    op.create_table(
        "agent_org_nodes",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reports_to", sa.String(255), nullable=True),
        sa.Column(
            "org_role",
            sa.String(50),
            nullable=False,
            server_default="worker",
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        *_common_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", name="uq_agent_org_nodes_agent_id"),
    )
    op.create_index(
        "ix_agent_org_nodes_agent_id",
        "agent_org_nodes",
        ["agent_id"],
    )
    op.create_index(
        "ix_agent_org_nodes_reports_to",
        "agent_org_nodes",
        ["reports_to"],
    )
    op.create_index(
        "ix_agent_org_nodes_org_role",
        "agent_org_nodes",
        ["org_role"],
    )


def downgrade() -> None:
    """Drop agent_org_nodes table (#1405)."""
    for idx, tbl in [
        ("ix_agent_org_nodes_org_role", "agent_org_nodes"),
        ("ix_agent_org_nodes_reports_to", "agent_org_nodes"),
        ("ix_agent_org_nodes_agent_id", "agent_org_nodes"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("agent_org_nodes")
