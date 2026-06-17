# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Create llc_routine_runs table.

Revision ID: 20260523_035
Revises: 20260523_034
Create Date: 2026-05-23 00:00:00.000000

GH#8229: Each row records a single execution of an LLC routine.
heartbeat_run_id links to llc_heartbeat_runs when that migration is present;
the FK is SET NULL so rows survive if the referenced run is deleted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260523_035"
down_revision: Union[str, None] = "20260523_034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_routine_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "routine_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_routines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "heartbeat_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "work_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_llc_routine_runs_routine_id", "llc_routine_runs", ["routine_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_routine_runs_routine_id", table_name="llc_routine_runs")
    op.drop_table("llc_routine_runs")
