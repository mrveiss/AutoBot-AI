# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC agent_org_nodes heartbeat scheduler fields.

Revision ID: 20260523_036
Revises: 20260523_035
Create Date: 2026-05-23

GH#8225: Extends agent_org_nodes with heartbeat scheduler columns so the
HeartbeatScheduler can load agent configurations on startup and update
last_heartbeat_at after each successful invocation.

Note: llc_heartbeat_runs table is created by migration 20260523_033 (PR #8481).
      llc_routine / llc_routine_runs tables are created by migrations
      20260523_034 and 20260523_035 (PR #8488). This migration runs after both.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260523_036"
down_revision: Union[str, None] = "20260523_035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_column("agent_org_nodes", "context_mode")
    op.drop_column("agent_org_nodes", "adapter_config")
    op.drop_column("agent_org_nodes", "adapter_type")
    op.drop_column("agent_org_nodes", "last_heartbeat_at")
    op.drop_column("agent_org_nodes", "heartbeat_enabled")
    op.drop_column("agent_org_nodes", "heartbeat_cron")
