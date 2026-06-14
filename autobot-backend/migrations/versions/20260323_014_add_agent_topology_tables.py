# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Add agent topology tables: agent_connections, agent_task_history (#2177, #2137).

Revision ID: 20260323_014
Revises: 20260323_013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260323_014"
down_revision = "20260323_013"
branch_labels = None
depends_on = None


def _create_agent_connections_table() -> None:
    """Create agent_connections table. Helper for upgrade() (#2177)."""
    op.create_table(
        "agent_connections",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("from_agent", sa.Text, nullable=False),
        sa.Column("to_agent", sa.Text, nullable=False),
        sa.Column("task_type", sa.Text, nullable=True),
        sa.Column("weight", sa.Float, nullable=True, server_default="0.5"),
        sa.Column(
            "co_success_count",
            sa.Integer,
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "co_failure_count",
            sa.Integer,
            nullable=True,
            server_default="0",
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "from_agent",
            "to_agent",
            "task_type",
            name="uq_agent_connections",
        ),
    )
    _create_agent_connections_indexes()


def _create_agent_connections_indexes() -> None:
    """Create indexes for agent_connections. Helper (#2177)."""
    op.create_index(
        "idx_agent_conn_from",
        "agent_connections",
        ["from_agent"],
    )
    op.create_index(
        "idx_agent_conn_weight",
        "agent_connections",
        ["from_agent", "weight"],
    )


def _create_agent_task_history_table() -> None:
    """Create agent_task_history table. Helper for upgrade() (#2177)."""
    op.create_table(
        "agent_task_history",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("agent_id", sa.Text, nullable=False),
        sa.Column("task_type", sa.Text, nullable=False),
        sa.Column("workflow_id", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("execution_time_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.func.now(),
        ),
    )
    _create_agent_task_history_indexes()


def _create_agent_task_history_indexes() -> None:
    """Create indexes for agent_task_history. Helper (#2177)."""
    op.create_index(
        "idx_agent_history_agent",
        "agent_task_history",
        ["agent_id", "created_at"],
    )
    op.create_index(
        "idx_agent_history_task",
        "agent_task_history",
        ["task_type"],
    )


def upgrade() -> None:
    """Create agent_connections and agent_task_history tables."""
    _create_agent_connections_table()
    _create_agent_task_history_table()


def downgrade() -> None:
    """Drop agent topology tables in reverse order."""
    op.drop_index("idx_agent_history_task", table_name="agent_task_history")
    op.drop_index("idx_agent_history_agent", table_name="agent_task_history")
    op.drop_table("agent_task_history")

    op.drop_index("idx_agent_conn_weight", table_name="agent_connections")
    op.drop_index("idx_agent_conn_from", table_name="agent_connections")
    op.drop_table("agent_connections")
