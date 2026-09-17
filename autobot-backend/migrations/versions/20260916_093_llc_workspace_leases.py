# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Give an agent workspace an owner and an expiry (#16818).

Company OS has always used workspaces and never owned one. The adapters shell out to a
git worktree; nothing in the domain recorded who held it or when it should come back, so
disposal was a shell script inferring intent from a coordination ledger outside the
domain entirely.

What that cost, observed on 2026-09-16: the worktree ceiling refused a new workspace and
blocked a release-pipeline fix. The reaper found four workspaces whose branches were
fully merged and correctly refused all four -- three claimed by a session that no longer
existed, and a claim with no expiry cannot be reclaimed by anyone but its claimant.
Merged work held slots nothing could release.

``NO DATA LOSS``: this revision creates one new table and touches nothing else.
``downgrade`` drops exactly that table. No existing row is read, written or migrated --
leases begin being recorded when something starts recording them, and a workspace that
predates this table is simply not represented, which is the state we are already in.

``path`` is UNIQUE on purpose: two live leases on one directory is the collision the
ledger exists to prevent, so the database refuses it rather than leaving it to callers.
The FK to ``llc_heartbeat_runs`` is ON DELETE SET NULL rather than CASCADE -- losing the
run must not delete the lease, because an orphaned lease is precisely what needs
reclaiming and a deleted row cannot be reclaimed.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.guards import has_table

logger = logging.getLogger(__name__)

revision: str = "20260916_093"
down_revision: Union[str, None] = "20260914_092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("llc_workspace_leases"):
        return  # already applied
    op.create_table(
        "llc_workspace_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("heartbeat_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch", sa.Text(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["heartbeat_run_id"], ["llc_heartbeat_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path", name="uq_llc_workspace_leases_path"),
    )
    op.create_index("ix_llc_workspace_leases_company_id", "llc_workspace_leases", ["company_id"])
    op.create_index("ix_llc_workspace_leases_owner", "llc_workspace_leases", ["owner"])
    op.create_index("ix_llc_workspace_leases_heartbeat_run_id", "llc_workspace_leases", ["heartbeat_run_id"])
    op.create_index("ix_llc_workspace_leases_acquired_at", "llc_workspace_leases", ["acquired_at"])
    # The sweep's query is "live and past its deadline", so expires_at and
    # released_at are the two it filters on. Indexed together rather than
    # separately: a reclaim scan that has to seq-scan the table is a reclaim
    # that gets switched off the first time the table is large.
    op.create_index("ix_llc_workspace_leases_expiry", "llc_workspace_leases", ["released_at", "expires_at"])
    logger.info("#16818: llc_workspace_leases created; leases are recorded from here on")


def downgrade() -> None:
    if has_table("llc_workspace_leases"):
        op.drop_table("llc_workspace_leases")
