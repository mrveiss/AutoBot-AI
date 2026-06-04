"""Create llc_approvals table and approval enum types.

Revision ID: 20260523_027
Revises: 20260523_026
Create Date: 2026-05-23 00:00:00.000000

GH#8214: Board approval gates — hire, strategy, budget_override, sprint_close.
Creates the ``approvaltype`` and ``approvalstatus`` PostgreSQL enums plus the
``llc_approvals`` table.  Both enums are created with ``checkfirst=True`` to
handle re-runs and pre-existing partial migrations gracefully.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260523_027"
down_revision: Union[str, None] = "20260523_026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_approvaltype = sa.Enum(
    "hire",
    "strategy",
    "budget_override",
    "sprint_close",
    name="approvaltype",
)

_approvalstatus = sa.Enum(
    "pending",
    "approved",
    "rejected",
    "withdrawn",
    "expired",
    name="approvalstatus",
)


def upgrade() -> None:
    # Create enum types independently so they survive partial rollbacks.
    _approvaltype.create(op.get_bind(), checkfirst=True)
    _approvalstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "llc_approvals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "hire",
                "strategy",
                "budget_override",
                "sprint_close",
                name="approvaltype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "withdrawn",
                "expired",
                name="approvalstatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_by_agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "payload",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("decided_by_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_llc_approvals_company_id", "llc_approvals", ["company_id"])
    op.create_index("ix_llc_approvals_type", "llc_approvals", ["type"])
    op.create_index("ix_llc_approvals_status", "llc_approvals", ["status"])
    op.create_index(
        "ix_llc_approvals_requested_by_agent_id",
        "llc_approvals",
        ["requested_by_agent_id"],
    )
    # Compound index for the most common query: pending approvals for a company.
    op.create_index(
        "ix_llc_approvals_company_status",
        "llc_approvals",
        ["company_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_llc_approvals_company_status", table_name="llc_approvals")
    op.drop_index("ix_llc_approvals_requested_by_agent_id", table_name="llc_approvals")
    op.drop_index("ix_llc_approvals_status", table_name="llc_approvals")
    op.drop_index("ix_llc_approvals_type", table_name="llc_approvals")
    op.drop_index("ix_llc_approvals_company_id", table_name="llc_approvals")
    op.drop_table("llc_approvals")
    _approvalstatus.drop(op.get_bind(), checkfirst=True)
    _approvaltype.drop(op.get_bind(), checkfirst=True)
