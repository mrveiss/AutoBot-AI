# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add llc_work_items reviewer columns + llc_sprints.kb_summary (schema drift fix).

The ORM models declare ``reviewer_user_id`` / ``reviewer_agent_id``
(llc/models/work_item.py) and ``kb_summary`` (llc/models/sprint.py), but no
migration ever added them, so every work-item and sprint read raised asyncpg
``UndefinedColumnError`` (boards, backlog, sprint summary/close all 500'd).

Forward-only drift reconciliation, idempotent (``ADD COLUMN IF NOT EXISTS``).

Revision ID: 20260630_064
Revises: 20260629_063
"""
from typing import Sequence, Union

from alembic import op

from migrations.guards import has_table

# revision identifiers, used by Alembic.
revision: str = "20260630_064"
down_revision: Union[str, None] = "20260629_063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("llc_work_items"):
        op.execute('ALTER TABLE "llc_work_items" ADD COLUMN IF NOT EXISTS reviewer_user_id UUID')
        op.execute('ALTER TABLE "llc_work_items" ADD COLUMN IF NOT EXISTS reviewer_agent_id UUID')
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_llc_work_items_reviewer_user_id '
            'ON "llc_work_items" (reviewer_user_id)'
        )
        op.execute(
            'CREATE INDEX IF NOT EXISTS ix_llc_work_items_reviewer_agent_id '
            'ON "llc_work_items" (reviewer_agent_id)'
        )

    if has_table("llc_sprints"):
        op.execute('ALTER TABLE "llc_sprints" ADD COLUMN IF NOT EXISTS kb_summary TEXT')


def downgrade() -> None:
    # Forward-only drift reconciliation: dropping these re-breaks the ORM read
    # paths they fix, so downgrade is a no-op (matches 20260629_063).
    pass
