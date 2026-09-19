# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add company_id to approvals and copy every llc_approvals row onto it (#17043).

Revision ID: 20260918_094
Revises: 20260916_093
Create Date: 2026-09-18 00:00:00.000000

Two approval systems never knew about each other: the platform-general
``approvals`` (unscoped) and the LLC ``llc_approvals`` (company-scoped).
This migration makes ``approvals`` the single table for both -- a NULL
``company_id`` means platform-general, a set one means the LLC case --
and copies every existing ``llc_approvals`` row onto it, keyed by the same
``id`` so an approval already handed out by ``llc_approvals.id`` still
resolves after the merge.

``llc_approvals`` itself is left in place, untouched, read-only from here
on: dropping it is a separate, later, reviewed step once the unified path
is verified live, not bundled into the same change that migrates off it.

``approvals.decided_at`` was ``TIMESTAMP WITHOUT TIME ZONE`` (#006), while
``llc_approvals.decided_at`` was always ``TIMESTAMP WITH TIME ZONE`` (#027).
Copying tz-aware values into a naive column silently drops the offset --
caught by #17072 CI, not by review, since a same-instant UTC value compares
unequal only as Python objects, not in the stored bytes. Fixed at the
schema, not by normalising the test's comparison: the naive type was wrong
the moment this table started receiving tz-aware data.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_094"
down_revision: Union[str, None] = "20260916_093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COPY_SQL = """
    INSERT INTO approvals (
        id, title, description, approval_type, status, company_id,
        requested_by_agent, decided_by_user, context, decided_at,
        created_at, updated_at
    )
    SELECT
        id,
        type::text || ' approval',
        NULL,
        type::text,
        status::text,
        company_id,
        requested_by_agent_id::text,
        decided_by_agent_id::text,
        payload,
        decided_at,
        created_at,
        updated_at
    FROM llc_approvals
    ON CONFLICT (id) DO NOTHING
"""


def upgrade() -> None:
    op.add_column("approvals", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_approvals_company_id", "approvals", ["company_id"])
    op.create_index("ix_approvals_company_status", "approvals", ["company_id", "status"])
    op.alter_column("approvals", "decided_at", type_=sa.DateTime(timezone=True))

    bind = op.get_bind()
    before = bind.execute(sa.text("SELECT COUNT(*) FROM llc_approvals")).scalar()
    bind.execute(sa.text(_COPY_SQL))
    after = bind.execute(sa.text("SELECT COUNT(*) FROM approvals WHERE id IN (SELECT id FROM llc_approvals)")).scalar()
    if after != before:
        raise RuntimeError(f"llc_approvals migration incomplete: {before} source rows, {after} copied onto approvals")


_UNSAFE_COPIED_ROWS_SQL = """
    SELECT COUNT(*)
    FROM approvals a
    JOIN llc_approvals la ON la.id = a.id
    WHERE a.updated_at > la.updated_at
       OR EXISTS (SELECT 1 FROM approval_comments c WHERE c.approval_id = a.id)
       OR EXISTS (SELECT 1 FROM task_approval_links t WHERE t.approval_id = a.id)
"""


def downgrade() -> None:
    """Conditionally refused (#17043 review, #17072 CI follow-up): a copied
    row is safe to drop only when nothing has touched it through the unified
    table since the copy -- no comment, no task link, and no decision (its
    ``updated_at`` still matches the source row's). On an untouched DB
    (including a fresh migration-test one) that holds for every row, so the
    downgrade round-trips; once anything has happened through the unified
    path, it refuses rather than cascade that data away.
    """
    bind = op.get_bind()
    unsafe = bind.execute(sa.text(_UNSAFE_COPIED_ROWS_SQL)).scalar()
    if unsafe:
        raise NotImplementedError(
            f"20260918_094 downgrade is refused: {unsafe} copied row(s) have a comment, a task "
            "link, or a decision recorded since the copy ran. Undoing this migration would drop "
            "that data. Reverse by hand after confirming no unified row has changed since "
            "cutover -- see this function's docstring."
        )

    bind.execute(sa.text("DELETE FROM approvals WHERE id IN (SELECT id FROM llc_approvals)"))
    op.alter_column("approvals", "decided_at", type_=sa.DateTime(timezone=False))
    op.drop_index("ix_approvals_company_status", table_name="approvals")
    op.drop_index("ix_approvals_company_id", table_name="approvals")
    op.drop_column("approvals", "company_id")
