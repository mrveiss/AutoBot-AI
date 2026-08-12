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

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_073"
down_revision: Union[str, None] = "20260811_072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_org_nodes",
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            # Literal, not an import of LLCAgentStatus.AVAILABLE — migrations
            # in this tree never import application code, only stdlib/sa/op.
            server_default="available",
        ),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("pause_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_org_nodes",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_org_nodes", "paused_at")
    op.drop_column("agent_org_nodes", "pause_reason")
    op.drop_column("agent_org_nodes", "status")
