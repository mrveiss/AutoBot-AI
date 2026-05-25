# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add co-worker columns to llc_work_items (GH#8230 follow-up).

Revision ID: 20260525_040
Revises: 20260525_039
Create Date: 2026-05-25

GH#8515: PR #8514 added co-working columns to LLCWorkItem but did not include
a migration. This adds the 4 missing columns so the DB schema matches the ORM.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260525_040"
down_revision: Union[str, None] = "20260525_039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llc_work_items", sa.Column("co_worker_type", sa.String(16), nullable=True))
    op.add_column("llc_work_items", sa.Column("co_worker_agent_id", UUID(as_uuid=True), nullable=True))
    op.add_column("llc_work_items", sa.Column("co_worker_user_id", UUID(as_uuid=True), nullable=True))
    op.add_column(
        "llc_work_items",
        sa.Column("co_working_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_llc_work_items_co_worker_agent_id", "llc_work_items", ["co_worker_agent_id"])
    op.create_index("ix_llc_work_items_co_worker_user_id", "llc_work_items", ["co_worker_user_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_work_items_co_worker_user_id", table_name="llc_work_items")
    op.drop_index("ix_llc_work_items_co_worker_agent_id", table_name="llc_work_items")
    op.drop_column("llc_work_items", "co_working_enabled")
    op.drop_column("llc_work_items", "co_worker_user_id")
    op.drop_column("llc_work_items", "co_worker_agent_id")
    op.drop_column("llc_work_items", "co_worker_type")
