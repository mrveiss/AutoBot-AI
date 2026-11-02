# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-company switch: raising a budget limit needs a board approval (#8214).

Revision ID: 20261101_109
Revises: 20261101_108
Create Date: 2026-11-01 00:00:09.000000

``NO DATA LOSS``: one additive NOT NULL column with a server default of false, so every existing company
keeps today's behaviour (a raise by an admin applies at once) and no row is rewritten by hand. Guarded for a
database that ``create_all`` already built. Downgrade drops the column; the setting is the only thing lost.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column

revision: str = "20261101_109"
down_revision: Union[str, None] = "20261101_108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN = "require_approval_for_budget_raises"


def upgrade() -> None:
    if not has_column("organizations", _COLUMN):
        op.add_column(
            "organizations",
            sa.Column(
                "require_approval_for_budget_raises", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )


def downgrade() -> None:
    if has_column("organizations", _COLUMN):
        op.drop_column("organizations", _COLUMN)
