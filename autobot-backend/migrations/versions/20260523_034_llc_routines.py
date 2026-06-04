"""Create llc_routines table.

Revision ID: 20260523_034
Revises: 20260523_033
Create Date: 2026-05-23 00:00:00.000000

GH#8229: LLC Routines — recurring agent tasks defined by a cron schedule.
Chains from 20260523_033 (llc_heartbeat_runs, merged via PR #8481).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260523_034"
down_revision: Union[str, None] = "20260523_033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_routines",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("cron_schedule", sa.Text, nullable=False),
        sa.Column("assignee_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("env", JSONB, nullable=True),
        sa.Column(
            "produces",
            sa.String(32),
            nullable=False,
            server_default="new_work_item",
        ),
        sa.Column("work_item_template", JSONB, nullable=True),
        sa.Column(
            "recurring_work_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_routines_company_id", "llc_routines", ["company_id"])
    op.create_index("ix_llc_routines_assignee_agent_id", "llc_routines", ["assignee_agent_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_routines_assignee_agent_id", table_name="llc_routines")
    op.drop_index("ix_llc_routines_company_id", table_name="llc_routines")
    op.drop_table("llc_routines")
