"""Add view tracking and login requirement to chat shared links (GH#8996).

Adds:
- view_count: Number of times link has been accessed
- last_accessed_at: Timestamp of last access
- require_login: If True, only authenticated users can access

Revision ID: 20260605_051
Revises: 20260531_050
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_051"
down_revision: Union[str, None] = "20260531_050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add view_count column (default 0)
    op.add_column(
        "chat_shared_links",
        sa.Column(
            "view_count",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Number of times this link has been accessed",
        ),
    )

    # Add last_accessed_at column (nullable, no default)
    op.add_column(
        "chat_shared_links",
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of the last access; NULL if never accessed",
        ),
    )

    # Add require_login column (default False)
    op.add_column(
        "chat_shared_links",
        sa.Column(
            "require_login",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="If True, only authenticated users can access (no public access)",
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_shared_links", "require_login")
    op.drop_column("chat_shared_links", "last_accessed_at")
    op.drop_column("chat_shared_links", "view_count")
