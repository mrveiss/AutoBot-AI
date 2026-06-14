# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add hierarchical access levels to secrets

Revision ID: 002
Revises: 001
Create Date: 2026-02-16

Issue #685: Add org_id and team_ids for hierarchical secret access

Issue #9759: the ``secrets`` table was historically created only by
``Base.metadata.create_all`` (models/secret.py), never by any migration, so on
a fresh database this revision's ``add_column`` hit a missing relation and the
whole upgrade chain aborted. The table is now created here (in its pre-002
shape) when absent; databases that already have it — via create_all or an
earlier upgrade run — skip creation, and the column adds are guarded the same
way because a create_all-built table already carries them.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.guards import existing_columns, has_table

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_secrets_table() -> None:
    """Create the pre-002 ``secrets`` table (models/secret.py as of Issue #870)."""
    op.create_table(
        "secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User ID who owns this secret",
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            comment="Visibility scope: user, session, or shared",
        ),
        sa.Column(
            "session_id",
            sa.String(128),
            nullable=True,
            comment="Session ID for session-scoped secrets",
        ),
        sa.Column("shared_with", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "encrypted_value",
            sa.Text(),
            nullable=False,
            comment="Fernet-encrypted secret value",
        ),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("extra_data", postgresql.JSONB, nullable=False, server_default="{}"),
        # Inherited from the declarative Base (user_management/models/base.py),
        # so every create_all-built secrets table carries them and the ORM
        # always selects them.
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
    op.create_index("ix_secrets_owner_id", "secrets", ["owner_id"])
    op.create_index("ix_secrets_name", "secrets", ["name"])
    op.create_index("ix_secrets_type", "secrets", ["type"])
    op.create_index("ix_secrets_scope", "secrets", ["scope"])
    op.create_index("ix_secrets_session_id", "secrets", ["session_id"])


def upgrade() -> None:
    """Ensure secrets table exists, then add org_id/team_ids for hierarchical access."""
    if not has_table("secrets"):
        _create_secrets_table()
        present_columns: set[str] = set()
    else:
        # Table predates migration control (created via create_all) — it may
        # already carry any of the columns this revision adds.
        present_columns = existing_columns("secrets")

    if "org_id" not in present_columns:
        op.add_column(
            "secrets",
            sa.Column(
                "org_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Organization ID for org-level secrets (Issue #685)",
            ),
        )
        op.create_index(
            "ix_secrets_org_id",
            "secrets",
            ["org_id"],
        )

    if "team_ids" not in present_columns:
        op.add_column(
            "secrets",
            sa.Column(
                "team_ids",
                postgresql.JSONB,
                nullable=False,
                server_default="[]",
                comment="Array of team IDs for group-scoped secrets (Issue #685)",
            ),
        )

    # Update scope column comment to reflect new options
    op.alter_column(
        "secrets",
        "scope",
        comment="Visibility scope: user, session, shared, group, or organization",
    )


def downgrade() -> None:
    """Remove org_id and team_ids columns from secrets table.

    Intentionally NOT the inverse of upgrade(): the secrets table itself is
    left in place even when upgrade() created it, matching the historical
    create_all-owned state that revision 001 never managed (#9759).
    """
    # Remove team_ids column
    op.drop_column("secrets", "team_ids")

    # Remove org_id index and column
    op.drop_index("ix_secrets_org_id", table_name="secrets")
    op.drop_column("secrets", "org_id")

    # Restore original scope comment
    op.alter_column(
        "secrets",
        "scope",
        comment="Visibility scope: user, session, or shared",
    )
