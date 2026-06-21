# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Convert naive DateTime columns to TIMESTAMPTZ in skills and process_run tables.

skill_packages.created_at, skill_packages.promoted_at, skill_repos.last_synced,
skill_approvals.requested_at, skill_approvals.reviewed_at, process_runs.started_at,
process_runs.completed_at, agent_sessions.expires_at.

Revision ID: 20260422_018
Revises: 20260324_017
Issue #5538 — DateTime(timezone=True) for skills and process_run models.

Issue #9759: every table here is created by ``create_all`` at app startup
(skills/models.py via _init_skills_tables, models/process_run.py), never by a
migration, so on a fresh database the unconditional ALTERs aborted the chain.
Absent tables are skipped — their models already declare
``DateTime(timezone=True)``, so create_all builds them in post-018 shape.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

revision: str = "20260422_018"
down_revision: str | None = "20260324_017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = [
    ("skill_packages", "created_at"),
    ("skill_packages", "promoted_at"),
    ("skill_repos", "last_synced"),
    ("skill_approvals", "requested_at"),
    ("skill_approvals", "reviewed_at"),
    ("process_runs", "started_at"),
    ("process_runs", "completed_at"),
    ("agent_sessions", "expires_at"),
]


def upgrade() -> None:
    """Convert naive TIMESTAMP columns to TIMESTAMPTZ. Issue #5538."""
    for table, column in _COLUMNS:
        if not has_table(table):
            continue
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Revert TIMESTAMPTZ columns back to naive TIMESTAMP. Issue #5538."""
    for table, column in _COLUMNS:
        if not has_table(table):
            continue
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=False),
        )
