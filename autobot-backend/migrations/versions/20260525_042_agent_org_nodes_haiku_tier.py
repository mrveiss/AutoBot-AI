# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add model and instructions_file_path columns to agent_org_nodes (GH#8486).

Revision ID: 20260525_042
Revises: 20260525_041
Create Date: 2026-05-25

GH#8486: Two-tier Haiku assistant architecture.
- model: the Anthropic model identifier for this agent (e.g. claude-haiku-4-5-20251001).
  When NULL, the adapter falls back to its own default (claude-sonnet-4-6).
- instructions_file_path: absolute path to the AGENTS.md file for this agent.
  The LLC health probe flags agents with heartbeat_enabled=true that have no
  instructions file or whose file does not exist on disk.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_042"
down_revision: Union[str, None] = "20260525_041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_org_nodes",
        sa.Column("model", sa.String(255), nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("instructions_file_path", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_org_nodes", "instructions_file_path")
    op.drop_column("agent_org_nodes", "model")
