# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_run_replay_logs table for agent run replay/debugging (GH#9034).

Revision ID: 20260612_055
Revises: 20260611_054
Create Date: 2026-06-12 00:00:00.000000

Records the full inputs snapshot, agent config, captured events, and final
output for each heartbeat run so runs can be replayed and step-browsed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260612_055"
down_revision: Union[str, None] = "20260611_054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("llc_run_replay_logs"):
        return

    op.create_table(
        "llc_run_replay_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "replay_of_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("inputs_snapshot", JSONB, nullable=True),
        sa.Column("agent_snapshot", JSONB, nullable=True),
        sa.Column("recorded_events", JSONB, nullable=True),
        sa.Column("output_text", sa.Text, nullable=True),
        sa.Column("final_status", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_llc_run_replay_logs_run_id", "llc_run_replay_logs", ["run_id"])
    op.create_index(
        "ix_llc_run_replay_logs_replay_of_run_id",
        "llc_run_replay_logs",
        ["replay_of_run_id"],
    )
    op.create_index("ix_llc_run_replay_logs_company_id", "llc_run_replay_logs", ["company_id"])
    op.create_index("ix_llc_run_replay_logs_agent_id", "llc_run_replay_logs", ["agent_id"])
    op.create_index("ix_llc_run_replay_logs_created_at", "llc_run_replay_logs", ["created_at"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("llc_run_replay_logs"):
        return
    op.drop_index("ix_llc_run_replay_logs_created_at", "llc_run_replay_logs")
    op.drop_index("ix_llc_run_replay_logs_agent_id", "llc_run_replay_logs")
    op.drop_index("ix_llc_run_replay_logs_company_id", "llc_run_replay_logs")
    op.drop_index("ix_llc_run_replay_logs_replay_of_run_id", "llc_run_replay_logs")
    op.drop_index("ix_llc_run_replay_logs_run_id", "llc_run_replay_logs")
    op.drop_table("llc_run_replay_logs")
