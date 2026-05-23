"""LLC heartbeat scheduler: llc_heartbeat_runs + agent_org_nodes extensions.

Revision ID: 20260523_033
Revises: 20260523_032
Create Date: 2026-05-23

GH#8225: Adds the llc_heartbeat_runs table and extends agent_org_nodes with
heartbeat scheduler fields (cron expression, enabled flag, adapter config,
context mode) so the HeartbeatScheduler can persist run records and load
agent configurations on startup.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260523_033"
down_revision: Union[str, None] = "20260523_032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend agent_org_nodes with heartbeat scheduler fields (GH#8225)
    # ------------------------------------------------------------------
    op.add_column(
        "agent_org_nodes",
        sa.Column("heartbeat_cron", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column(
            "heartbeat_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("adapter_type", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("adapter_config", JSONB, nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column(
            "context_mode",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'thin'"),
        ),
    )

    # ------------------------------------------------------------------
    # llc_heartbeat_runs table (GH#8225)
    # ------------------------------------------------------------------
    op.create_table(
        "llc_heartbeat_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", sa.String(255), nullable=False, index=True),
        sa.Column("agent_id", sa.String(255), nullable=False, index=True),
        sa.Column(
            "invocation_source",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'scheduler'"),
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("external_run_id", sa.Text(), nullable=True),
        sa.Column("context_snapshot", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_llc_heartbeat_runs_agent_id", "llc_heartbeat_runs", ["agent_id"])
    op.create_index("ix_llc_heartbeat_runs_company_id", "llc_heartbeat_runs", ["company_id"])
    op.create_index("ix_llc_heartbeat_runs_status", "llc_heartbeat_runs", ["status"])
    op.create_index("ix_llc_heartbeat_runs_created_at", "llc_heartbeat_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llc_heartbeat_runs_created_at", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_status", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_company_id", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_agent_id", table_name="llc_heartbeat_runs")
    op.drop_table("llc_heartbeat_runs")
    op.drop_column("agent_org_nodes", "context_mode")
    op.drop_column("agent_org_nodes", "adapter_config")
    op.drop_column("agent_org_nodes", "adapter_type")
    op.drop_column("agent_org_nodes", "last_heartbeat_at")
    op.drop_column("agent_org_nodes", "heartbeat_enabled")
    op.drop_column("agent_org_nodes", "heartbeat_cron")
