"""Add review_brief JSONB column to llc_work_items.

Revision ID: 20260524_036
Revises: 20260523_035
Create Date: 2026-05-24 00:00:00.000000

GH#8232: Human→Agent handoff writes a structured context brief into
``review_brief`` so the picking agent immediately sees who handed off,
the human notes summary, and whether the notes were KB-indexed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260524_036"
down_revision: Union[str, None] = "20260523_035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column("review_brief", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "review_brief")
