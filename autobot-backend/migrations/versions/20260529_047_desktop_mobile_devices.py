"""Add desktop_mobile_devices table for mobile device pairing (GH#4463).

Revision ID: 20260529_047
Revises: 20260528_046
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_047"
down_revision: Union[str, None] = "20260528_046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "desktop_mobile_devices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        # No index=True: the explicit op.create_index below builds the same
        # ix_desktop_mobile_devices_user_id, and the duplicate CREATE INDEX
        # aborted fresh-database upgrades (#9759).
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("device_name", sa.String(255), nullable=False),
        sa.Column("device_token", sa.Text, nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_desktop_mobile_devices_user_id",
        "desktop_mobile_devices",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_desktop_mobile_devices_user_id", table_name="desktop_mobile_devices")
    op.drop_table("desktop_mobile_devices")
