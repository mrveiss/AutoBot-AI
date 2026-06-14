# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add process adapter tables for background task decomposition

Revision ID: 20260315_010
Revises: 20260315_009
Create Date: 2026-03-15 12:00:00.000000

Issue #1406: Process adapters with subprocess lifecycle management,
task decomposition, and agent session persistence.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260315_010"
down_revision = "20260315_009"
branch_labels = None
depends_on = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_UUID = postgresql.UUID(as_uuid=True)


def _common_ts_cols():
    """Return created_at/updated_at Column defs. Helper (#1406)."""
    return [
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    ]


def _create_process_runs_table() -> None:
    """Create process_runs table. Helper for upgrade() (#1406)."""
    op.create_table(
        "process_runs",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=True),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("args", _JSONB, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("signal", sa.String(30), nullable=True),
        sa.Column("log_excerpt", sa.Text(), nullable=True),
        sa.Column("log_path", sa.String(1024), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        *_common_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_process_runs_agent_id", "process_runs", ["agent_id"])
    op.create_index("ix_process_runs_task_id", "process_runs", ["task_id"])
    op.create_index("ix_process_runs_status", "process_runs", ["status"])


def _create_task_decompositions_table() -> None:
    """Create task_decompositions table. Helper for upgrade() (#1406)."""
    op.create_table(
        "task_decompositions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("parent_task_id", sa.String(255), nullable=False),
        sa.Column("subtask_order", sa.Integer(), nullable=False),
        sa.Column("process_run_id", _UUID, nullable=False),
        sa.Column("depends_on", _JSONB, nullable=True),
        sa.Column("context_in", _JSONB, nullable=True),
        sa.Column("context_out", _JSONB, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        *_common_ts_cols(),
        sa.ForeignKeyConstraint(["process_run_id"], ["process_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_decompositions_parent_task_id",
        "task_decompositions",
        ["parent_task_id"],
    )
    op.create_index(
        "ix_task_decompositions_process_run_id",
        "task_decompositions",
        ["process_run_id"],
    )
    op.create_index("ix_task_decompositions_status", "task_decompositions", ["status"])


def _create_agent_sessions_table() -> None:
    """Create agent_sessions table. Helper for upgrade() (#1406)."""
    op.create_table(
        "agent_sessions",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False),
        sa.Column("session_state", _JSONB, nullable=True),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        *_common_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_sessions_agent_id", "agent_sessions", ["agent_id"])
    op.create_index("ix_agent_sessions_task_id", "agent_sessions", ["task_id"])
    op.create_index("ix_agent_sessions_expires_at", "agent_sessions", ["expires_at"])


def upgrade() -> None:
    """Create process adapter tables (#1406)."""
    _create_process_runs_table()
    _create_task_decompositions_table()
    _create_agent_sessions_table()


def downgrade() -> None:
    """Drop process adapter tables (#1406)."""
    for idx, tbl in [
        ("ix_agent_sessions_expires_at", "agent_sessions"),
        ("ix_agent_sessions_task_id", "agent_sessions"),
        ("ix_agent_sessions_agent_id", "agent_sessions"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("agent_sessions")
    for idx, tbl in [
        ("ix_task_decompositions_status", "task_decompositions"),
        ("ix_task_decompositions_process_run_id", "task_decompositions"),
        ("ix_task_decompositions_parent_task_id", "task_decompositions"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("task_decompositions")
    for idx, tbl in [
        ("ix_process_runs_status", "process_runs"),
        ("ix_process_runs_task_id", "process_runs"),
        ("ix_process_runs_agent_id", "process_runs"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("process_runs")
