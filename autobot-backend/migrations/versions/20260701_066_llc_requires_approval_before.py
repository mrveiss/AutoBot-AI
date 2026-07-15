# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add requires_approval_before to llc_work_items (GH#11140).

Revision ID: 20260701_066
Revises: 20260630_065
Create Date: 2026-07-01 00:00:00.000000

Adds a JSONB ``requires_approval_before`` column to ``llc_work_items`` storing
the list of declarative approval-gated action categories (e.g. "pushing commits",
"publishing", "destructive operations"). Makes governance visible at plan time;
runtime enforcement stays in the existing approval flow. Defaults to an empty
list so existing rows keep their current (no declared gates) behaviour.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260701_066"
down_revision: Union[str, None] = "20260630_065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column(
            "requires_approval_before",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "requires_approval_before")
