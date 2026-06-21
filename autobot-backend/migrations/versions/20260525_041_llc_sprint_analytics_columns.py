# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add velocity_actual, capacity_points, projection to llc_sprints (GH#8474).

Revision ID: 20260525_041
Revises: 20260525_040
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_041"
down_revision: Union[str, None] = "20260525_040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llc_sprints", sa.Column("velocity_actual", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("llc_sprints", sa.Column("capacity_points", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("llc_sprints", sa.Column("projection", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("llc_sprints", "projection")
    op.drop_column("llc_sprints", "capacity_points")
    op.drop_column("llc_sprints", "velocity_actual")
