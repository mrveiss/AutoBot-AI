"""Add heartbeat system tables for scheduled agent wakeups

Revision ID: 20260309_007
Revises: 20260307_006
Create Date: 2026-03-09 12:00:00.000000

Issue #1407: Heartbeat system with scheduled agent wakeups and session persistence
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260309_007"
down_revision = "20260307_006"
branch_labels = None
depends_on = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_UUID = postgresql.UUID(as_uuid=True)


def _common_ts_cols():
    """Return created_at/updated_at Column defs. Helper (#1407)."""
    return [
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
    ]


def _create_agent_runtime_state_table() -> None:
    """Create agent_runtime_state table. Helper for upgrade() (#1407)."""
    op.create_table(
        "agent_runtime_state",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column(
            "heartbeat_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "heartbeat_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        sa.Column(
            "max_run_duration_seconds",
            sa.Integer(),
            nullable=False,
            server_default="600",
        ),
        sa.Column("current_task_id", sa.String(255), nullable=True),
        sa.Column("session_params", _JSONB, nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("extra", _JSONB, nullable=True),
        *_common_ts_cols(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", name="uq_agent_runtime_state_agent_id"),
    )
    op.create_index(
        "ix_agent_runtime_state_agent_id", "agent_runtime_state", ["agent_id"]
    )
    op.create_index(
        "ix_agent_runtime_state_current_task_id",
        "agent_runtime_state",
        ["current_task_id"],
    )


def _create_heartbeat_runs_table() -> None:
    """Create heartbeat_runs table. Helper for upgrade() (#1407)."""
    op.create_table(
        "heartbeat_runs",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("runtime_state_id", _UUID, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(30), nullable=False, server_default="interval"),
        sa.Column("wakeup_context", _JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_common_ts_cols(),
        sa.ForeignKeyConstraint(
            ["runtime_state_id"], ["agent_runtime_state.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_heartbeat_runs_agent_id", "heartbeat_runs", ["agent_id"])
    op.create_index(
        "ix_heartbeat_runs_runtime_state_id", "heartbeat_runs", ["runtime_state_id"]
    )
    op.create_index("ix_heartbeat_runs_status", "heartbeat_runs", ["status"])


def _create_heartbeat_run_events_table() -> None:
    """Create heartbeat_run_events table. Helper for upgrade() (#1407)."""
    op.create_table(
        "heartbeat_run_events",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("run_id", _UUID, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", _JSONB, nullable=True),
        sa.Column("occurred_at", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["heartbeat_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_heartbeat_run_events_run_id", "heartbeat_run_events", ["run_id"]
    )
    op.create_index(
        "ix_heartbeat_run_events_event_type", "heartbeat_run_events", ["event_type"]
    )


def _create_agent_wakeup_requests_table() -> None:
    """Create agent_wakeup_requests table. Helper for upgrade() (#1407)."""
    op.create_table(
        "agent_wakeup_requests",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("runtime_state_id", _UUID, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context", _JSONB, nullable=True),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_by_run_id", _UUID, nullable=True),
        *_common_ts_cols(),
        sa.ForeignKeyConstraint(
            ["runtime_state_id"], ["agent_runtime_state.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_wakeup_requests_agent_id", "agent_wakeup_requests", ["agent_id"]
    )
    op.create_index(
        "ix_agent_wakeup_requests_priority", "agent_wakeup_requests", ["priority"]
    )
    op.create_index(
        "ix_agent_wakeup_requests_runtime_state_id",
        "agent_wakeup_requests",
        ["runtime_state_id"],
    )


def upgrade() -> None:
    """Create heartbeat system tables."""
    _create_agent_runtime_state_table()
    _create_heartbeat_runs_table()
    _create_heartbeat_run_events_table()
    _create_agent_wakeup_requests_table()


def downgrade() -> None:
    """Drop heartbeat system tables."""
    for idx, tbl in [
        ("ix_agent_wakeup_requests_runtime_state_id", "agent_wakeup_requests"),
        ("ix_agent_wakeup_requests_priority", "agent_wakeup_requests"),
        ("ix_agent_wakeup_requests_agent_id", "agent_wakeup_requests"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("agent_wakeup_requests")
    for idx, tbl in [
        ("ix_heartbeat_run_events_event_type", "heartbeat_run_events"),
        ("ix_heartbeat_run_events_run_id", "heartbeat_run_events"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("heartbeat_run_events")
    for idx, tbl in [
        ("ix_heartbeat_runs_status", "heartbeat_runs"),
        ("ix_heartbeat_runs_runtime_state_id", "heartbeat_runs"),
        ("ix_heartbeat_runs_agent_id", "heartbeat_runs"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("heartbeat_runs")
    for idx, tbl in [
        ("ix_agent_runtime_state_current_task_id", "agent_runtime_state"),
        ("ix_agent_runtime_state_agent_id", "agent_runtime_state"),
    ]:
        op.drop_index(idx, table_name=tbl)
    op.drop_table("agent_runtime_state")
