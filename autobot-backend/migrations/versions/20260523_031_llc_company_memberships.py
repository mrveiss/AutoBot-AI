# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC company memberships table (GH#8223).

Adds:
  - ``llc_company_memberships`` — human user membership in an LLC company
    with role enum (owner, admin, member, guest).
  - ``assignee_user_id`` already exists on ``llc_work_items``; this migration
    adds no work-item columns — claim/unclaim operate via the existing field.

Revision ID: 20260523_031
Revises: 20260523_030
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "20260523_031"
down_revision = "20260523_030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE membershiprole AS ENUM ('owner', 'admin', 'member', 'guest')")

    op.create_table(
        "llc_company_memberships",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            # postgresql.ENUM: generic sa.Enum silently IGNORES create_type,
            # re-emitting CREATE TYPE after the op.execute above and aborting
            # fresh-database upgrades (#9759).
            ENUM(
                "owner",
                "admin",
                "member",
                "guest",
                name="membershiprole",
                create_type=False,
            ),
            nullable=False,
            server_default="member",
        ),
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
        sa.UniqueConstraint("company_id", "user_id", name="uq_llc_membership_company_user"),
    )

    op.create_index(
        "ix_llc_company_memberships_company_id",
        "llc_company_memberships",
        ["company_id"],
    )
    op.create_index(
        "ix_llc_company_memberships_user_id",
        "llc_company_memberships",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_llc_company_memberships_user_id", table_name="llc_company_memberships")
    op.drop_index("ix_llc_company_memberships_company_id", table_name="llc_company_memberships")
    op.drop_table("llc_company_memberships")
    op.execute("DROP TYPE IF EXISTS membershiprole")
