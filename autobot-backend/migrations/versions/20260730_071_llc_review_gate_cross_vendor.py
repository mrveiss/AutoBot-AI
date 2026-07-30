# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add requires_cross_vendor_review to llc_review_gate_policies (#12618).

Revision ID: 20260730_071
Revises: 20260710_070
Create Date: 2026-07-30 00:00:00.000000

Adds a non-nullable boolean column, server-defaulted to ``false``, so existing
rows are unaffected and no data is lost. Mirrors the existing
``requires_human_review`` column: per-company, per-item-type opt-in for the
cross-vendor second-opinion verifier tier (design:
docs/design/2026-07-26-cross-vendor-review-gate.md). Ships off by default
company-wide; also gated globally by AUTOBOT_LLC_CROSS_VENDOR_REVIEW_ENABLED.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_071"
down_revision: Union[str, None] = "20260710_070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_review_gate_policies",
        sa.Column("requires_cross_vendor_review", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("llc_review_gate_policies", "requires_cross_vendor_review")
