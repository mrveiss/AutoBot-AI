# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add company_id to agent_org_nodes (GH#8225).

Revision ID: 20260523_037
Revises: 20260523_036
Create Date: 2026-05-23

GH#8225: The HeartbeatScheduler needs to know which company (UUID) each agent
belongs to in order to insert llc_heartbeat_runs.company_id (NOT NULL).

The column is nullable so existing rows are unaffected; operators must set it
when registering agents in the LLC context.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260523_037"
down_revision: Union[str, None] = "20260523_036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_org_nodes",
        sa.Column("company_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_agent_org_nodes_company_id",
        "agent_org_nodes",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_org_nodes_company_id", table_name="agent_org_nodes")
    op.drop_column("agent_org_nodes", "company_id")
