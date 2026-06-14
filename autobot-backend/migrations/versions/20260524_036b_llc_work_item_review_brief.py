# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add review_brief JSONB column to llc_work_items.

Renamed from 20260524_036 → 20260524_036b to resolve duplicate revision ID
conflict with 20260524_036_llc_review_gate_policies.py.

Revision ID: 20260524_036b
Revises: 20260524_036
Create Date: 2026-05-24 00:00:00.000000

GH#8232: Human→Agent handoff writes a structured context brief into
``review_brief`` so the picking agent immediately sees who handed off,
the human notes summary, and whether the notes were KB-indexed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from alembic import op

revision: str = "20260524_036b"
down_revision: Union[str, None] = "20260524_036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column("review_brief", pg.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "review_brief")
