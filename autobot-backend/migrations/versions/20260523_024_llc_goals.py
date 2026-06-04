"""Create llc_goals table for 4-level goal hierarchy (GH#8212).

Revision ID: 20260523_024
Revises: 20260523_023
Create Date: 2026-05-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_024"
down_revision: Union[str, None] = "20260523_023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_goals",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("parent_goal_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("owner_agent_id", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_goal_id"],
            ["llc_goals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llc_goals_company_id", "llc_goals", ["company_id"])
    op.create_index("ix_llc_goals_parent_goal_id", "llc_goals", ["parent_goal_id"])
    op.create_index("ix_llc_goals_level", "llc_goals", ["level"])
    op.create_index("ix_llc_goals_status", "llc_goals", ["status"])
    op.create_index("ix_llc_goals_owner_agent_id", "llc_goals", ["owner_agent_id"])
    # llc_goals must exist before this FK can be wired — deferred from migration 022.
    op.create_foreign_key(
        "fk_llc_work_items_goal_id",
        "llc_work_items",
        "llc_goals",
        ["goal_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_llc_work_items_goal_id", "llc_work_items", type_="foreignkey")
    op.drop_index("ix_llc_goals_owner_agent_id", table_name="llc_goals")
    op.drop_index("ix_llc_goals_status", table_name="llc_goals")
    op.drop_index("ix_llc_goals_level", table_name="llc_goals")
    op.drop_index("ix_llc_goals_parent_goal_id", table_name="llc_goals")
    op.drop_index("ix_llc_goals_company_id", table_name="llc_goals")
    op.drop_table("llc_goals")
