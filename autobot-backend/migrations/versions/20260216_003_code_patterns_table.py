"""Add code_patterns table for pattern extraction

Revision ID: 20260216_003
Revises: 20260216_002
Create Date: 2026-02-16 20:50:00.000000

Issue #903: Pattern Extraction Infrastructure
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260216_003"
down_revision = "20260216_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create code_patterns table."""
    op.create_table(
        "code_patterns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pattern_type", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column("times_suggested", sa.Integer(), nullable=True),
        sa.Column("times_accepted", sa.Integer(), nullable=True),
        sa.Column("acceptance_rate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for fast lookup
    op.create_index(
        "ix_pattern_lookup", "code_patterns", ["pattern_type", "language", "category"]
    )
    op.create_index(
        "ix_pattern_frequency", "code_patterns", ["frequency", "acceptance_rate"]
    )
    op.create_index(
        "ix_pattern_language_type", "code_patterns", ["language", "pattern_type"]
    )
    op.create_index(
        op.f("ix_code_patterns_pattern_type"), "code_patterns", ["pattern_type"]
    )
    op.create_index(op.f("ix_code_patterns_language"), "code_patterns", ["language"])
    op.create_index(op.f("ix_code_patterns_category"), "code_patterns", ["category"])
    op.create_index(op.f("ix_code_patterns_frequency"), "code_patterns", ["frequency"])
    op.create_index(
        op.f("ix_code_patterns_acceptance_rate"), "code_patterns", ["acceptance_rate"]
    )


def downgrade() -> None:
    """Drop code_patterns table."""
    op.drop_index(op.f("ix_code_patterns_acceptance_rate"), table_name="code_patterns")
    op.drop_index(op.f("ix_code_patterns_frequency"), table_name="code_patterns")
    op.drop_index(op.f("ix_code_patterns_category"), table_name="code_patterns")
    op.drop_index(op.f("ix_code_patterns_language"), table_name="code_patterns")
    op.drop_index(op.f("ix_code_patterns_pattern_type"), table_name="code_patterns")
    op.drop_index("ix_pattern_language_type", table_name="code_patterns")
    op.drop_index("ix_pattern_frequency", table_name="code_patterns")
    op.drop_index("ix_pattern_lookup", table_name="code_patterns")
    op.drop_table("code_patterns")
