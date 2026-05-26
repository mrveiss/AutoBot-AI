"""Backfill AgentRuntimeState.status from heartbeat_enabled and drop the column (GH#6476).

Existing rows where heartbeat_enabled=false get status='disabled'.
Rows where heartbeat_enabled=true already have status='active' (set by the
previous migration's server_default); no update needed for those.
Finally, drop the now-redundant heartbeat_enabled column.

Revision ID: 20260526_044
Revises: 20260525_043
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_044"
down_revision: Union[str, None] = "20260525_043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Backfill: agents that were disabled should become 'disabled', not 'active'
    conn.execute(
        sa.text(
            "UPDATE agent_runtime_state SET status = 'disabled' "
            "WHERE heartbeat_enabled = false AND status = 'active'"
        )
    )
    op.drop_column("agent_runtime_state", "heartbeat_enabled")


def downgrade() -> None:
    op.add_column(
        "agent_runtime_state",
        sa.Column("heartbeat_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE agent_runtime_state SET heartbeat_enabled = true "
            "WHERE status = 'active'"
        )
    )
