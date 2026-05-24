"""LLC agent API keys table (GH#8218).

Revision ID: 20260523_029
Revises: 20260523_028
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20260523_029"
down_revision = "20260523_028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llc_agent_api_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("key_hash", sa.Text, nullable=False, unique=True),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_llc_api_keys_agent_id", "llc_agent_api_keys", ["agent_id"])
    op.create_index("ix_llc_api_keys_company_id", "llc_agent_api_keys", ["company_id"])
    op.create_index("ix_llc_api_keys_key_hash", "llc_agent_api_keys", ["key_hash"])


def downgrade() -> None:
    op.drop_table("llc_agent_api_keys")
