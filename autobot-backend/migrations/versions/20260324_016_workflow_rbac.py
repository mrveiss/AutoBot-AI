# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Add workflow_permissions and workflow_audit_log tables (#2152).

Revision ID: 20260324_016
Revises: 20260324_015
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "20260324_016"
down_revision = "20260324_015"
branch_labels = None
depends_on = None


def _create_workflow_permissions_table() -> None:
    """Create workflow_permissions table. Helper for upgrade() (#2152)."""
    op.create_table(
        "workflow_permissions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workflow_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=True),
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
        sa.UniqueConstraint("workflow_id", "user_id", name="uq_workflow_permission"),
    )
    _create_workflow_permissions_indexes()


def _create_workflow_permissions_indexes() -> None:
    """Create indexes for workflow_permissions. Helper (#2152)."""
    op.create_index(
        "idx_wp_workflow_id",
        "workflow_permissions",
        ["workflow_id"],
    )
    op.create_index(
        "idx_wp_user_id",
        "workflow_permissions",
        ["user_id"],
    )


def _create_workflow_audit_log_table() -> None:
    """Create workflow_audit_log table. Helper for upgrade() (#2152)."""
    op.create_table(
        "workflow_audit_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("workflow_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("details", JSONB, nullable=True),
    )
    _create_workflow_audit_log_indexes()


def _create_workflow_audit_log_indexes() -> None:
    """Create indexes for workflow_audit_log. Helper (#2152)."""
    op.create_index(
        "idx_wal_workflow_id",
        "workflow_audit_log",
        ["workflow_id"],
    )
    op.create_index(
        "idx_wal_user_id",
        "workflow_audit_log",
        ["user_id"],
    )
    op.create_index(
        "idx_wal_timestamp",
        "workflow_audit_log",
        ["timestamp"],
    )
    op.create_index(
        "idx_wal_action",
        "workflow_audit_log",
        ["action"],
    )


def upgrade() -> None:
    """Create workflow_permissions and workflow_audit_log tables."""
    _create_workflow_permissions_table()
    _create_workflow_audit_log_table()


def downgrade() -> None:
    """Drop workflow RBAC tables in reverse dependency order."""
    op.drop_index("idx_wal_action", table_name="workflow_audit_log")
    op.drop_index("idx_wal_timestamp", table_name="workflow_audit_log")
    op.drop_index("idx_wal_user_id", table_name="workflow_audit_log")
    op.drop_index("idx_wal_workflow_id", table_name="workflow_audit_log")
    op.drop_table("workflow_audit_log")

    op.drop_index("idx_wp_user_id", table_name="workflow_permissions")
    op.drop_index("idx_wp_workflow_id", table_name="workflow_permissions")
    op.drop_table("workflow_permissions")
