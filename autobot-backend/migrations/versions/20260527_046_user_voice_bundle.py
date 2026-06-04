"""Add user_voice_bundle table for per-user voice bundle assignment (GH#8605).

Revision ID: 20260527_046
Revises: 20260526_045
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_046"
down_revision: Union[str, None] = "20260526_045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_voice_bundle",
        sa.Column("user_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("bundle_name", sa.String(64), nullable=False),
        sa.Column("assigned_by", sa.String(64), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_voice_bundle")
