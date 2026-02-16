"""Add completion_feedback table for learning loop

Revision ID: 20260216_005
Revises: 20260216_004
Create Date: 2026-02-16 22:00:00.000000

Issue #905: Learning Loop Feedback System
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260216_005"
down_revision = "20260216_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create completion_feedback table."""
    op.create_table(
        "completion_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("pattern_id", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.String(length=10), nullable=True),
        sa.Column("completion_rank", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for fast queries
    op.create_index(
        op.f("ix_completion_feedback_timestamp"),
        "completion_feedback",
        ["timestamp"],
    )
    op.create_index(
        op.f("ix_completion_feedback_user_id"), "completion_feedback", ["user_id"]
    )
    op.create_index(
        op.f("ix_completion_feedback_action"), "completion_feedback", ["action"]
    )
    op.create_index(
        op.f("ix_completion_feedback_pattern_id"),
        "completion_feedback",
        ["pattern_id"],
    )


def downgrade() -> None:
    """Drop completion_feedback table."""
    op.drop_index(
        op.f("ix_completion_feedback_pattern_id"), table_name="completion_feedback"
    )
    op.drop_index(
        op.f("ix_completion_feedback_action"), table_name="completion_feedback"
    )
    op.drop_index(
        op.f("ix_completion_feedback_user_id"), table_name="completion_feedback"
    )
    op.drop_index(
        op.f("ix_completion_feedback_timestamp"), table_name="completion_feedback"
    )
    op.drop_table("completion_feedback")
