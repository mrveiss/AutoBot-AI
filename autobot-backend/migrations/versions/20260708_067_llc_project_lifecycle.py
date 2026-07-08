# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add project archive→dispose lifecycle columns + PROJECT_DISPOSAL approval type (#11129 P2)."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Merge migration: unifies the two dangling heads left by Phase 1 (#11129) —
# 20260707_066 (project_code_source) and 20260701_066 (requires_approval_before)
# both descended from 20260630_065, creating "Multiple head revisions". See #11253.
# This revision is BOTH a merge (two parents) AND functional (adds lifecycle columns);
# Alembic runs upgrade() exactly once, after both parents are confirmed applied.
revision: str = "20260708_067"
down_revision: Union[str, Sequence[str], None] = ("20260707_066", "20260701_066")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LIFECYCLE = sa.Enum(
    "active", "archived", "pending_disposal", "disposed", name="projectlifecyclestate"
)


def upgrade() -> None:
    bind = op.get_bind()
    _LIFECYCLE.create(bind, checkfirst=True)
    op.add_column(
        "llc_projects",
        sa.Column(
            "lifecycle_state",
            _LIFECYCLE,
            nullable=False,
            server_default=sa.text("'active'::projectlifecyclestate"),
        ),
    )
    op.create_index("ix_llc_projects_lifecycle_state", "llc_projects", ["lifecycle_state"])
    op.add_column("llc_projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "llc_projects", sa.Column("disposal_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "llc_projects",
        sa.Column("disposal_approval_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE approvaltype ADD VALUE IF NOT EXISTS 'project_disposal'")


def downgrade() -> None:
    op.drop_index("ix_llc_projects_lifecycle_state", table_name="llc_projects")
    op.drop_column("llc_projects", "disposal_approval_id")
    op.drop_column("llc_projects", "disposal_scheduled_at")
    op.drop_column("llc_projects", "archived_at")
    op.drop_column("llc_projects", "lifecycle_state")
    _LIFECYCLE.drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot drop an enum value; 'project_disposal' remains on approvaltype (harmless).
