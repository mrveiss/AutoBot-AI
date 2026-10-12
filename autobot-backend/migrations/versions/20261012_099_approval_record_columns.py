# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add the one-approval-record columns to approvals (#13421, slice S1).

Revision ID: 20261012_099
Revises: 20261011_098
Create Date: 2026-10-12 00:00:00.000000

Seven approval surfaces each kept their own pending state. ``approvals`` is already the
canonical record (#17043), so it is extended -- not replaced -- with six NULLABLE columns:

* ``source``       -- which surface raised it (``models.approval.ApprovalSource``)
* ``risk_tier``    -- ``autobot_shared.risk_tier.RiskTier`` (lowercase low..critical)
* ``expires_at``   -- when an undecided approval stops being decidable
* ``payload_hash`` -- sha256 of the proposed payload, binding a decision to what was shown
* ``resume_ref``   -- opaque key the source's resume handler uses to continue the work
* ``owner_user``   -- username owning the raising session; scopes the pending list (#18413)

Every existing row keeps NULL in all five: nothing is rewritten and no row is added or
removed, which the upgrade asserts with a row count (the 094 pattern).

The downgrade drops columns, which would discard whatever the unified path wrote into
them, so it refuses once any row carries a value in one of the five.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_099"
down_revision: Union[str, None] = "20261011_098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_COLUMNS = ("source", "risk_tier", "expires_at", "payload_hash", "resume_ref", "owner_user")

_POPULATED_SQL = (
    "SELECT COUNT(*) FROM approvals WHERE source IS NOT NULL OR risk_tier IS NOT NULL "
    "OR expires_at IS NOT NULL OR payload_hash IS NOT NULL OR resume_ref IS NOT NULL OR owner_user IS NOT NULL"
)


def upgrade() -> None:
    bind = op.get_bind()
    before = bind.execute(sa.text("SELECT COUNT(*) FROM approvals")).scalar()

    op.add_column("approvals", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("approvals", sa.Column("risk_tier", sa.String(20), nullable=True))
    op.add_column("approvals", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvals", sa.Column("payload_hash", sa.String(64), nullable=True))
    op.add_column("approvals", sa.Column("resume_ref", sa.String(255), nullable=True))
    op.add_column("approvals", sa.Column("owner_user", sa.String(255), nullable=True))
    op.create_index("ix_approvals_source", "approvals", ["source"])
    op.create_index("ix_approvals_risk_tier", "approvals", ["risk_tier"])
    op.create_index("ix_approvals_owner_user", "approvals", ["owner_user"])

    after = bind.execute(sa.text("SELECT COUNT(*) FROM approvals")).scalar()
    populated = bind.execute(sa.text(_POPULATED_SQL)).scalar()
    if after != before or populated:
        raise RuntimeError(
            f"approvals column migration touched existing rows: {before} rows before, {after} after, "
            f"{populated} with a value in a new column (expected {before}, {before}, 0)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(sa.text(_POPULATED_SQL)).scalar()
    if populated:
        raise NotImplementedError(
            f"20261012_099 downgrade is refused: {populated} approval row(s) carry a source, risk_tier, "
            "expires_at, payload_hash, resume_ref or owner_user value. Dropping the columns would discard it. "
            "Reverse by hand once those rows are exported or no longer needed."
        )
    op.drop_index("ix_approvals_owner_user", table_name="approvals")
    op.drop_index("ix_approvals_risk_tier", table_name="approvals")
    op.drop_index("ix_approvals_source", table_name="approvals")
    for name in reversed(_NEW_COLUMNS):
        op.drop_column("approvals", name)
