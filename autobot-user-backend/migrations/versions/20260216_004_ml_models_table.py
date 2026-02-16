"""Add ml_models table for model registry

Revision ID: 20260216_004
Revises: 20260216_003
Create Date: 2026-02-16 21:30:00.000000

Issue #904: ML Model Training Pipeline
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260216_004"
down_revision = "20260216_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ml_models table."""
    op.create_table(
        "ml_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("pattern_type", sa.String(length=50), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("val_loss", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("mrr", sa.Float(), nullable=True),
        sa.Column("hit_at_1", sa.Float(), nullable=True),
        sa.Column("hit_at_5", sa.Float(), nullable=True),
        sa.Column("hit_at_10", sa.Float(), nullable=True),
        sa.Column("epochs_trained", sa.Integer(), nullable=True),
        sa.Column("training_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("num_parameters", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(op.f("ix_ml_models_version"), "ml_models", ["version"], unique=True)
    op.create_index(op.f("ix_ml_models_is_active"), "ml_models", ["is_active"])


def downgrade() -> None:
    """Drop ml_models table."""
    op.drop_index(op.f("ix_ml_models_is_active"), table_name="ml_models")
    op.drop_index(op.f("ix_ml_models_version"), table_name="ml_models")
    op.drop_table("ml_models")
