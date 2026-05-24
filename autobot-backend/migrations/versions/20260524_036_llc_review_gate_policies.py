"""Create llc_review_gate_policies table.

Revision ID: 20260524_036
Revises: 20260523_035
Create Date: 2026-05-24 00:00:00.000000

GH#8234: One row per (company_id, item_type) pair — configures whether human
review is required before a work item of that type can be transitioned to done.
reviewer_role is a nullable text field referencing a MembershipRole value;
NULL means any company member with review privilege can approve.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260524_036"
down_revision: Union[str, None] = "20260523_035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_review_gate_policies",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "item_type",
            sa.Enum(
                "epic", "feature", "pbi", "task", "bug", "subtask", "spike", "risk",
                name="workitemtype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reviewer_role", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llc_review_gate_policies_company_id", "llc_review_gate_policies", ["company_id"])
    op.create_unique_constraint(
        "uq_review_gate_company_item_type",
        "llc_review_gate_policies",
        ["company_id", "item_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_review_gate_company_item_type", "llc_review_gate_policies")
    op.drop_index("ix_llc_review_gate_policies_company_id", table_name="llc_review_gate_policies")
    op.drop_table("llc_review_gate_policies")
