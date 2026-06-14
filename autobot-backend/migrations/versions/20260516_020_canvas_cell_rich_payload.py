# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add rich_payload JSONB column to canvas_cell for Phase 2 chart/code cells.

Revision ID: 20260516_020
Revises: 20260516_019
Create Date: 2026-05-16 12:00:00.000000

MVA-484: Phase 2A backend — Vega-Lite spec validation + rich payload storage.

Additive-only migration (spec §4 contract guarantee):
- Adds nullable rich_payload JSONB column.
- Phase 1 cells retain content=TEXT unchanged; rich_payload is null.
- No existing columns renamed or dropped.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260516_020"
down_revision: Union[str, None] = "20260516_019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "canvas_cell",
        sa.Column("rich_payload", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("canvas_cell", "rich_payload")
