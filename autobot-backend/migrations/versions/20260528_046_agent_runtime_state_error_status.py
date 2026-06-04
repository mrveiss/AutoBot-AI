"""Add error status support to AgentRuntimeState (MVA-1411, GH#6476).

Adds error_detail (Text), error_at (DateTime), error_code (String 64) columns
to agent_runtime_state.  The status column is already VARCHAR(32) so the new
'error' enum value requires no DDL change — only the new metadata columns.

Chain: 20260526_045 (status_migration) → 20260528_046 (this)

Revision ID: 20260528_046
Revises: 20260526_045
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_046"
down_revision: Union[str, None] = "20260526_045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runtime_state", sa.Column("error_detail", sa.Text(), nullable=True))
    op.add_column("agent_runtime_state", sa.Column("error_at", sa.DateTime(), nullable=True))
    op.add_column("agent_runtime_state", sa.Column("error_code", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runtime_state", "error_code")
    op.drop_column("agent_runtime_state", "error_at")
    op.drop_column("agent_runtime_state", "error_detail")
