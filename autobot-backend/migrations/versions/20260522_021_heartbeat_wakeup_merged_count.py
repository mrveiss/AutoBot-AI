# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add merged_count to agent_wakeup_requests for wakeup coalescing observability.

Revision ID: 20260522_021
Revises: 20260516_020
Create Date: 2026-05-22 00:00:00.000000

GH#6472: Pre-insert dedup in HeartbeatScheduler.wakeup() coalesces repeated
wakeup signals for the same (agent_id, task_id) into one row.  This column
tracks how many extra signals were merged, enabling tuning visibility.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260522_021"
down_revision: Union[str, None] = "20260516_020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_wakeup_requests",
        sa.Column("merged_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("agent_wakeup_requests", "merged_count")
