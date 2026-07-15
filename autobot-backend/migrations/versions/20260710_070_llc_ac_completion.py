# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add acceptance_criteria_done to llc_work_items (GH#10852).

Revision ID: 20260710_070
Revises: 20260708_069
Create Date: 2026-07-10 00:00:00.000000

Adds a JSONB ``acceptance_criteria_done`` column to ``llc_work_items`` storing a
list of booleans parallel-indexed to ``acceptance_criteria`` — the per-criterion
completion state that the WorkItemDetail checkboxes toggle. Before this the
checkboxes were local-only display state (``saveAC()`` was a no-op), so toggles
never persisted and were lost on reload. Nullable (matching ``acceptance_criteria``);
NULL means "no completion tracked yet" and existing rows keep their behaviour.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260710_070"
down_revision: Union[str, None] = "20260708_069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column("acceptance_criteria_done", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "acceptance_criteria_done")
