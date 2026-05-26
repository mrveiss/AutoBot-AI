"""Add workspace fields to agent_runtime_state (GH#6471).

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
    op.add_column(
        "agent_runtime_state",
        sa.Column("workspace_dir", sa.String(1024), nullable=True),
    )
    op.add_column(
        "agent_runtime_state",
        sa.Column("preview_url", sa.String(512), nullable=True),
    )
    op.add_column(
        "agent_runtime_state",
        sa.Column("preview_port", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runtime_state", "workspace_dir")
    op.drop_column("agent_runtime_state", "preview_url")
    op.drop_column("agent_runtime_state", "preview_port")
