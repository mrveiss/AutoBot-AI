# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Create llc_finding_proposals table + findingproposalstatus enum (#11271)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260708_069"
down_revision: Union[str, Sequence[str], None] = "20260708_068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FINDING_STATUS = sa.Enum("pending", "promoted", "dismissed", name="findingproposalstatus")


def upgrade() -> None:
    bind = op.get_bind()
    _FINDING_STATUS.create(bind, checkfirst=True)
    op.create_table(
        "llc_finding_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("finding_key", sa.String(512), nullable=False),
        sa.Column("finding_type", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("line_number", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("suggestion", sa.Text, nullable=True),
        sa.Column("verdict_is_real", sa.Boolean, nullable=True),
        sa.Column("verdict_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("verdict_rationale", sa.Text, nullable=True),
        sa.Column("status", _FINDING_STATUS, nullable=False, server_default="pending"),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dismiss_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["llc_projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "finding_key", name="uq_finding_proposal_project_key"),
    )
    op.create_index("ix_llc_finding_proposals_company_id", "llc_finding_proposals", ["company_id"])
    op.create_index("ix_llc_finding_proposals_project_id", "llc_finding_proposals", ["project_id"])
    op.create_index("ix_llc_finding_proposals_status", "llc_finding_proposals", ["status"])
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE approvaltype ADD VALUE IF NOT EXISTS 'finding_promotion'")


def downgrade() -> None:
    op.drop_index("ix_llc_finding_proposals_status", table_name="llc_finding_proposals")
    op.drop_index("ix_llc_finding_proposals_project_id", table_name="llc_finding_proposals")
    op.drop_index("ix_llc_finding_proposals_company_id", table_name="llc_finding_proposals")
    op.drop_table("llc_finding_proposals")
    _FINDING_STATUS.drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot drop an enum value; 'finding_promotion' remains on approvaltype (harmless).
