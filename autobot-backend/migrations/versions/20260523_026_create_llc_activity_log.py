"""Create llc_activity_log table.

Revision ID: 20260523_026
Revises: 20260523_025
Create Date: 2026-05-23 00:00:00.000000

GH#8216: Immutable activity log — company-scoped, all-mutations coverage.
Append-only table (no UPDATE/DELETE at service layer).
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260523_026"
down_revision: str | None = "20260523_025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llc_activity_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column(
            "after_state",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_llc_activity_log_company_id", "llc_activity_log", ["company_id"])
    op.create_index(
        "ix_llc_activity_log_entity",
        "llc_activity_log",
        ["company_id", "entity_type", "entity_id"],
    )
    op.create_index(
        "ix_llc_activity_log_occurred_at",
        "llc_activity_log",
        ["company_id", "occurred_at"],
    )
    op.create_index(
        "ix_llc_activity_log_action",
        "llc_activity_log",
        ["company_id", "action"],
    )
    op.create_index(
        "ix_llc_activity_log_actor_agent",
        "llc_activity_log",
        ["actor_agent_id"],
    )
    op.create_index(
        "ix_llc_activity_log_actor_user",
        "llc_activity_log",
        ["actor_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llc_activity_log_actor_user", "llc_activity_log")
    op.drop_index("ix_llc_activity_log_actor_agent", "llc_activity_log")
    op.drop_index("ix_llc_activity_log_action", "llc_activity_log")
    op.drop_index("ix_llc_activity_log_occurred_at", "llc_activity_log")
    op.drop_index("ix_llc_activity_log_entity", "llc_activity_log")
    op.drop_index("ix_llc_activity_log_company_id", "llc_activity_log")
    op.drop_table("llc_activity_log")
