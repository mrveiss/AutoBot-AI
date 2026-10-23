# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The line for AI on each tool action, per company (#18430).

Owner rule 2026-10-12: AI has three lines per ACTION of every tool -- ``autonomous``,
``draft_then_send`` (AI drafts, a person sends, it waits in Approvals) and ``never``. An unset
line counts as line 2, so the ABSENCE of a row is the default and nothing is backfilled.

``NO DATA LOSS``: one new table; nothing that exists is touched. Guarded with ``has_table`` so a
database already carrying this shape does not hard-fail.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_102"
down_revision: Union[str, None] = "20261012_101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "llc_ai_lines" in inspector.get_table_names():
        return
    op.create_table(
        "llc_ai_lines",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        # The scope's id: a company's, or a user's when scope_kind is 'user' (personal lines, same store).
        sa.Column("company_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_kind", sa.String(10), server_default="company", nullable=False),
        sa.Column("action_key", sa.String(320), nullable=False),
        sa.Column("line", sa.String(30), nullable=False),
        sa.Column("approval_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scope_kind", "company_id", "action_key", name="uq_llc_ai_lines_scope_action"),
    )
    op.create_index("ix_llc_ai_lines_company_id", "llc_ai_lines", ["company_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "llc_ai_lines" in inspector.get_table_names():
        op.drop_index("ix_llc_ai_lines_company_id", table_name="llc_ai_lines")
        op.drop_table("llc_ai_lines")
