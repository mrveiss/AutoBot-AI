# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Migration 007: Add velocity_actual, capacity_points columns and project_id FK to llc_sprints (GH#8474).

After GH#8220 introduced sprint planning analytics, the llc_sprints table was
missing three schema elements required by SprintPlanningService:

  velocity_actual  FLOAT    NULL — actual velocity computed on sprint close
  capacity_points  INTEGER  NULL — total story-point capacity planned for the sprint
  FK llc_sprints.project_id -> llc_projects.id (RESTRICT) — previously the
    column existed without a DB-level foreign key constraint.
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    # Add velocity_actual column (FLOAT, nullable — populated on sprint close)
    op.add_column(
        "llc_sprints",
        sa.Column("velocity_actual", sa.Float, nullable=True),
    )

    # Add capacity_points column (INTEGER, nullable — set during sprint planning)
    op.add_column(
        "llc_sprints",
        sa.Column("capacity_points", sa.Integer, nullable=True),
    )

    # Add the missing FK constraint from llc_sprints.project_id -> llc_projects.id.
    # The column was created without the FK in the original GH#8219 table-create
    # migration; this migration adds the constraint retroactively.
    op.create_foreign_key(
        "fk_llc_sprints_project_id",
        "llc_sprints",
        "llc_projects",
        ["project_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_llc_sprints_project_id", "llc_sprints", type_="foreignkey")
    op.drop_column("llc_sprints", "capacity_points")
    op.drop_column("llc_sprints", "velocity_actual")
