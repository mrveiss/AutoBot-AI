# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Create activities tables with user attribution.

Issue #871 - Activity Entity Types (#608 Phase 4)

Revision ID: 003
Revises: 002
Create Date: 2026-02-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _create_terminal_activities_table() -> None:
    """
    Create terminal_activities table.

    Helper for upgrade() (Issue #871).
    """
    op.create_table(
        "terminal_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("command", sa.Text, nullable=False),
        sa.Column("working_directory", sa.String(1024), nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column(
            "secrets_used",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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


def _create_file_activities_table() -> None:
    """
    Create file_activities table.

    Helper for upgrade() (Issue #871).
    """
    op.create_table(
        "file_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("path", sa.String(2048), nullable=False),
        sa.Column("new_path", sa.String(2048), nullable=True),
        sa.Column("file_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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


def _create_browser_activities_table() -> None:
    """
    Create browser_activities table.

    Helper for upgrade() (Issue #871).
    """
    op.create_table(
        "browser_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("selector", sa.String(512), nullable=True),
        sa.Column("input_value", sa.Text, nullable=True),
        sa.Column(
            "secrets_used",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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


def _create_desktop_activities_table() -> None:
    """
    Create desktop_activities table.

    Helper for upgrade() (Issue #871).
    """
    op.create_table(
        "desktop_activities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("coordinates", postgresql.ARRAY(sa.Integer), nullable=True),
        sa.Column("window_title", sa.String(512), nullable=True),
        sa.Column("input_text", sa.Text, nullable=True),
        sa.Column("screenshot_path", sa.String(1024), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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


def _create_secret_usage_table() -> None:
    """
    Create secret_usage audit trail table.

    Helper for upgrade() (Issue #871).
    """
    op.create_table(
        "secret_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "secret_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("access_granted", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("denial_reason", sa.String(512), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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


def _create_activity_indices() -> None:
    """
    Create indices for activity tables.

    Helper for upgrade() (Issue #871).
    """
    # Terminal activities indices
    op.create_index("ix_terminal_user_id", "terminal_activities", ["user_id"])
    op.create_index("ix_terminal_session_id", "terminal_activities", ["session_id"])
    op.create_index("ix_terminal_timestamp", "terminal_activities", ["timestamp"])

    # File activities indices
    op.create_index("ix_file_user_id", "file_activities", ["user_id"])
    op.create_index("ix_file_session_id", "file_activities", ["session_id"])
    op.create_index("ix_file_operation", "file_activities", ["operation"])
    op.create_index("ix_file_timestamp", "file_activities", ["timestamp"])

    # Browser activities indices
    op.create_index("ix_browser_user_id", "browser_activities", ["user_id"])
    op.create_index("ix_browser_session_id", "browser_activities", ["session_id"])
    op.create_index("ix_browser_action", "browser_activities", ["action"])
    op.create_index("ix_browser_timestamp", "browser_activities", ["timestamp"])

    # Desktop activities indices
    op.create_index("ix_desktop_user_id", "desktop_activities", ["user_id"])
    op.create_index("ix_desktop_session_id", "desktop_activities", ["session_id"])
    op.create_index("ix_desktop_action", "desktop_activities", ["action"])
    op.create_index("ix_desktop_timestamp", "desktop_activities", ["timestamp"])

    # Secret usage indices
    op.create_index("ix_secret_usage_secret_id", "secret_usage", ["secret_id"])
    op.create_index("ix_secret_usage_user_id", "secret_usage", ["user_id"])
    op.create_index("ix_secret_usage_activity_type", "secret_usage", ["activity_type"])
    op.create_index("ix_secret_usage_activity_id", "secret_usage", ["activity_id"])
    op.create_index("ix_secret_usage_session_id", "secret_usage", ["session_id"])
    op.create_index("ix_secret_usage_timestamp", "secret_usage", ["timestamp"])

    # Composite indices for common query patterns
    op.create_index(
        "ix_secret_usage_user_secret",
        "secret_usage",
        ["user_id", "secret_id"],
        unique=False,
    )


def upgrade() -> None:
    """Create activity tables with user attribution."""
    _create_terminal_activities_table()
    _create_file_activities_table()
    _create_browser_activities_table()
    _create_desktop_activities_table()
    _create_secret_usage_table()
    _create_activity_indices()


def _drop_activity_indices() -> None:
    """
    Drop activity table indices.

    Helper for downgrade() (Issue #871).
    """
    # Composite indices
    op.drop_index("ix_secret_usage_user_secret", table_name="secret_usage")

    # Secret usage indices
    op.drop_index("ix_secret_usage_timestamp", table_name="secret_usage")
    op.drop_index("ix_secret_usage_session_id", table_name="secret_usage")
    op.drop_index("ix_secret_usage_activity_id", table_name="secret_usage")
    op.drop_index("ix_secret_usage_activity_type", table_name="secret_usage")
    op.drop_index("ix_secret_usage_user_id", table_name="secret_usage")
    op.drop_index("ix_secret_usage_secret_id", table_name="secret_usage")

    # Desktop activities indices
    op.drop_index("ix_desktop_timestamp", table_name="desktop_activities")
    op.drop_index("ix_desktop_action", table_name="desktop_activities")
    op.drop_index("ix_desktop_session_id", table_name="desktop_activities")
    op.drop_index("ix_desktop_user_id", table_name="desktop_activities")

    # Browser activities indices
    op.drop_index("ix_browser_timestamp", table_name="browser_activities")
    op.drop_index("ix_browser_action", table_name="browser_activities")
    op.drop_index("ix_browser_session_id", table_name="browser_activities")
    op.drop_index("ix_browser_user_id", table_name="browser_activities")

    # File activities indices
    op.drop_index("ix_file_timestamp", table_name="file_activities")
    op.drop_index("ix_file_operation", table_name="file_activities")
    op.drop_index("ix_file_session_id", table_name="file_activities")
    op.drop_index("ix_file_user_id", table_name="file_activities")

    # Terminal activities indices
    op.drop_index("ix_terminal_timestamp", table_name="terminal_activities")
    op.drop_index("ix_terminal_session_id", table_name="terminal_activities")
    op.drop_index("ix_terminal_user_id", table_name="terminal_activities")


def downgrade() -> None:
    """Drop activity tables."""
    _drop_activity_indices()
    op.drop_table("secret_usage")
    op.drop_table("desktop_activities")
    op.drop_table("browser_activities")
    op.drop_table("file_activities")
    op.drop_table("terminal_activities")
