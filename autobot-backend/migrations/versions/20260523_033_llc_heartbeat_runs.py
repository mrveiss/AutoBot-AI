# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create llc_heartbeat_runs table (GH#8228).

Revision ID: 20260523_033
Revises: 20260523_032
Create Date: 2026-05-23

Minimal schema required by LivenessMonitor (GH#8228) to detect and expire
stuck runs. The full HeartbeatScheduler (GH#8225) populates rows; this
migration only defines the table so both issues can land independently.

status values: queued | running | succeeded | failed | cancelled | timed_out
invocation_source values: scheduler | manual | callback
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
    op.create_table(
        "llc_heartbeat_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("invocation_source", sa.String(32), nullable=False, server_default="scheduler"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column(
            "work_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("external_run_id", sa.Text, nullable=True),
        sa.Column("context_snapshot", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_heartbeat_runs_company_id", "llc_heartbeat_runs", ["company_id"])
    op.create_index("ix_llc_heartbeat_runs_agent_id", "llc_heartbeat_runs", ["agent_id"])
    op.create_index("ix_llc_heartbeat_runs_status", "llc_heartbeat_runs", ["status"])
    op.create_index("ix_llc_heartbeat_runs_started_at", "llc_heartbeat_runs", ["started_at"])
    op.create_index("ix_llc_heartbeat_runs_work_item_id", "llc_heartbeat_runs", ["work_item_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_heartbeat_runs_work_item_id", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_started_at", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_status", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_agent_id", table_name="llc_heartbeat_runs")
    op.drop_index("ix_llc_heartbeat_runs_company_id", table_name="llc_heartbeat_runs")
    op.drop_table("llc_heartbeat_runs")
