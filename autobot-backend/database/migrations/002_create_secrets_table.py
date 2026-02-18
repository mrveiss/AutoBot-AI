# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Create secrets table with ownership model.

Issue #870 - User Entity & Secrets Ownership Model (#608 Phase 1-2)

Revision ID: 002
Revises: 001
Create Date: 2026-02-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _create_secrets_table() -> None:
    """
    Create secrets table with all columns.

    Helper for upgrade() (Issue #870).
    """
    op.create_table(
        "secrets",
        # Primary key
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Ownership
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User ID who owns this secret",
        ),
        # Identity
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        # Scoping
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            server_default="user",
            comment="Visibility scope: user, session, or shared",
        ),
        sa.Column(
            "session_id",
            sa.String(128),
            nullable=True,
            comment="Session ID for session-scoped secrets",
        ),
        sa.Column(
            "shared_with",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment="Array of user IDs for shared secrets",
        ),
        # Encrypted value
        sa.Column(
            "encrypted_value",
            sa.Text,
            nullable=False,
            comment="Fernet-encrypted secret value",
        ),
        # Metadata
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        # Timestamps
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


def _create_secrets_indices() -> None:
    """
    Create indices for secrets table query performance.

    Helper for upgrade() (Issue #870).
    """
    op.create_index("ix_secrets_owner_id", "secrets", ["owner_id"])
    op.create_index("ix_secrets_name", "secrets", ["name"])
    op.create_index("ix_secrets_type", "secrets", ["type"])
    op.create_index("ix_secrets_scope", "secrets", ["scope"])
    op.create_index("ix_secrets_session_id", "secrets", ["session_id"])

    # Composite index for common query patterns
    op.create_index(
        "ix_secrets_owner_scope", "secrets", ["owner_id", "scope"], unique=False
    )


def upgrade() -> None:
    """Create secrets table with ownership and scoping."""
    _create_secrets_table()
    _create_secrets_indices()


def _drop_secrets_indices() -> None:
    """
    Drop indices from secrets table.

    Helper for downgrade() (Issue #870).
    """
    op.drop_index("ix_secrets_owner_scope", table_name="secrets")
    op.drop_index("ix_secrets_session_id", table_name="secrets")
    op.drop_index("ix_secrets_scope", table_name="secrets")
    op.drop_index("ix_secrets_type", table_name="secrets")
    op.drop_index("ix_secrets_name", table_name="secrets")
    op.drop_index("ix_secrets_owner_id", table_name="secrets")


def downgrade() -> None:
    """Drop secrets table."""
    _drop_secrets_indices()
    op.drop_table("secrets")
