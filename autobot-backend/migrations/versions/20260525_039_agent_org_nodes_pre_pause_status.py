"""Add pre_pause_status to agent_org_nodes (GH#8256 CR fix).

Revision ID: 20260525_039
Revises: 20260523_038
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_039"
down_revision: Union[str, None] = "20260523_038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_org_nodes", sa.Column("pre_pause_status", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_org_nodes", "pre_pause_status")
