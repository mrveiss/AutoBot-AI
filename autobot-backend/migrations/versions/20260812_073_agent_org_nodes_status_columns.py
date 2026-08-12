# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add status/pause_reason/paused_at to agent_org_nodes (#14108).

``llc/services/controls_service.py`` has read and written
``agent_org_nodes.status`` (plus ``pause_reason`` and ``paused_at``) via raw
SQL since GH#8256, but no migration ever created those columns — only the
sibling ``pre_pause_status`` (20260525_039) exists on the table. In any
database built strictly from this migration chain, every pause/resume/
terminate call fails at the SQL layer with an undefined-column error.

This is the root cause underneath #14108: the org-chart endpoint could never
have read a persisted lifecycle status because the column backing it did not
exist. Adding it here is a prerequisite for mapping ``status`` onto
``AgentOrgNode`` (models/agent_org.py) and having ``get_org_chart`` honor it.

Revision ID: 20260812_073
Revises: 20260811_072
Create Date: 2026-08-12 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

from migrations.guards import has_table

revision: str = "20260812_073"
down_revision: Union[str, None] = "20260811_072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guarded + IF NOT EXISTS, following 20260629_063 / 20260630_064, which
    # reconcile the same class of drift: raw SQL writing to a column no
    # migration ever created.
    #
    # This matters here specifically. #14108 records that we do NOT know whether
    # a deployed database already carries these columns from some out-of-band
    # path — settling that needs host evidence. A bare `op.add_column` would
    # hard-fail the deploy in exactly that case, so the migration must be
    # correct under both readings, not just the one we hope is true.
    if not has_table("agent_org_nodes"):
        return

    op.execute(
        'ALTER TABLE "agent_org_nodes" '
        "ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'available'"
    )
    op.execute('ALTER TABLE "agent_org_nodes" ADD COLUMN IF NOT EXISTS pause_reason TEXT')
    op.execute(
        'ALTER TABLE "agent_org_nodes" '
        "ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    # Symmetrically guarded: a downgrade must not fail on a database where the
    # columns were never present.
    if not has_table("agent_org_nodes"):
        return
    op.execute('ALTER TABLE "agent_org_nodes" DROP COLUMN IF EXISTS paused_at')
    op.execute('ALTER TABLE "agent_org_nodes" DROP COLUMN IF EXISTS pause_reason')
    op.execute('ALTER TABLE "agent_org_nodes" DROP COLUMN IF EXISTS status')
