"""Add approval gates tables for agent workflows

Revision ID: 20260307_006
Revises: 20260216_005
Create Date: 2026-03-07 12:00:00.000000

Issue #1402: Approval gates for agent workflows
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260307_006"
down_revision = "20260216_005"
branch_labels = None
depends_on = None


def _create_approvals_table() -> None:
    """Create approvals table. Helper for upgrade() (#1402)."""
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("approval_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_by_agent", sa.String(length=255), nullable=True),
        sa.Column("decided_by_user", sa.String(length=255), nullable=True),
        sa.Column("workflow_id", sa.String(length=255), nullable=True),
        sa.Column("workflow_step", sa.String(length=255), nullable=True),
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_approval_type", "approvals", ["approval_type"])
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.create_index(
        "ix_approvals_requested_by_agent",
        "approvals",
        ["requested_by_agent"],
    )
    op.create_index("ix_approvals_workflow_id", "approvals", ["workflow_id"])


def _create_comments_table() -> None:
    """Create approval_comments table. Helper for upgrade() (#1402)."""
    op.create_table(
        "approval_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column(
            "author_type",
            sa.String(length=20),
            nullable=False,
            server_default="human",
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_comments_approval_id",
        "approval_comments",
        ["approval_id"],
    )


def _create_task_links_table() -> None:
    """Create task_approval_links table. Helper for upgrade() (#1402)."""
    op.create_table(
        "task_approval_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column(
            "task_type",
            sa.String(length=50),
            nullable=False,
            server_default="github_issue",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_approval_links_approval_id",
        "task_approval_links",
        ["approval_id"],
    )
    op.create_index(
        "ix_task_approval_links_task_id",
        "task_approval_links",
        ["task_id"],
    )


def upgrade() -> None:
    """Create approvals, approval_comments, and task_approval_links."""
    _create_approvals_table()
    _create_comments_table()
    _create_task_links_table()


def downgrade() -> None:
    """Drop approval gates tables."""
    op.drop_index(
        "ix_task_approval_links_task_id",
        table_name="task_approval_links",
    )
    op.drop_index(
        "ix_task_approval_links_approval_id",
        table_name="task_approval_links",
    )
    op.drop_table("task_approval_links")

    op.drop_index(
        "ix_approval_comments_approval_id",
        table_name="approval_comments",
    )
    op.drop_table("approval_comments")

    op.drop_index("ix_approvals_workflow_id", table_name="approvals")
    op.drop_index("ix_approvals_requested_by_agent", table_name="approvals")
    op.drop_index("ix_approvals_status", table_name="approvals")
    op.drop_index("ix_approvals_approval_type", table_name="approvals")
    op.drop_table("approvals")
