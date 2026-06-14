# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add scheduled_start/scheduled_end to llc_work_items for the Gantt view (GH#9020).

Revision ID: 20260614_058
Revises: 20260614_057
Create Date: 2026-06-14 00:00:00.000000

Adds two optional planning-date columns to ``llc_work_items``. These are the
*planned* schedule used by the project timeline / Gantt view and are distinct
from the actual ``started_at`` / ``completed_at`` lifecycle timestamps.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_058"
down_revision: Union[str, None] = "20260614_057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "llc_work_items",
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "scheduled_end")
    op.drop_column("llc_work_items", "scheduled_start")
