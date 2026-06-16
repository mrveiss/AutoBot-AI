# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add retry_after and retry_count to llc_heartbeat_runs (GH#8502).

Revision ID: 20260523_038
Revises: 20260523_037
Create Date: 2026-05-24

retry_after  — when the HeartbeatScheduler should next re-dispatch this agent
               after a provider rate-limit (NULL = not rate-limited).
retry_count  — number of consecutive rate-limit retries (drives exponential
               backoff; reset to 0 on a successful run).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260523_038"
down_revision: Union[str, None] = "20260523_037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_heartbeat_runs",
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "llc_heartbeat_runs",
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_llc_heartbeat_runs_retry_after",
        "llc_heartbeat_runs",
        ["retry_after"],
        postgresql_where=sa.text("retry_after IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llc_heartbeat_runs_retry_after",
        table_name="llc_heartbeat_runs",
    )
    op.drop_column("llc_heartbeat_runs", "retry_count")
    op.drop_column("llc_heartbeat_runs", "retry_after")
