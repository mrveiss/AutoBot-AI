# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_agent_wiki_entries table for per-agent knowledge vault (GH#9021).

Revision ID: 20260531_050
Revises: 20260531_049
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260531_050"
down_revision: Union[str, None] = "20260531_049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_agent_wiki_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", sa.String(256), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=False, server_default="general"),
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_llc_agent_wiki_agent_id", "llc_agent_wiki_entries", ["agent_id"])
    op.create_index("ix_llc_agent_wiki_company_id", "llc_agent_wiki_entries", ["company_id"])
    op.create_index("ix_llc_agent_wiki_namespace", "llc_agent_wiki_entries", ["namespace"])
    op.create_unique_constraint(
        "uq_agent_wiki_agent_ns_key",
        "llc_agent_wiki_entries",
        ["agent_id", "namespace", "key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_agent_wiki_agent_ns_key", "llc_agent_wiki_entries", type_="unique")
    op.drop_index("ix_llc_agent_wiki_namespace", "llc_agent_wiki_entries")
    op.drop_index("ix_llc_agent_wiki_company_id", "llc_agent_wiki_entries")
    op.drop_index("ix_llc_agent_wiki_agent_id", "llc_agent_wiki_entries")
    op.drop_table("llc_agent_wiki_entries")
