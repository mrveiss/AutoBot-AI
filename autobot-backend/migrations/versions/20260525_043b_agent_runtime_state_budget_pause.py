"""Add budget pause fields to agent_runtime_state (GH#6470).

Renamed from 20260525_043 → 20260525_043b to resolve duplicate revision ID
conflict with 20260525_043_llc_membershiprole_add_lead.py.

Revision ID: 20260525_043b
Revises: 20260525_043
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_043b"
down_revision: Union[str, None] = "20260525_043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runtime_state",
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    )
    op.create_index(
        "ix_agent_runtime_state_status",
        "agent_runtime_state",
        ["status"],
    )
    op.add_column("agent_runtime_state", sa.Column("paused_reason", sa.Text, nullable=True))
    op.add_column("agent_runtime_state", sa.Column("paused_at", sa.DateTime, nullable=True))
    op.add_column("agent_runtime_state", sa.Column("paused_by", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_agent_runtime_state_status", table_name="agent_runtime_state")
    op.drop_column("agent_runtime_state", "status")
    op.drop_column("agent_runtime_state", "paused_reason")
    op.drop_column("agent_runtime_state", "paused_at")
    op.drop_column("agent_runtime_state", "paused_by")
