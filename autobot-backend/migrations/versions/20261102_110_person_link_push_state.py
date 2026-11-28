# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Record a failed push of a person's copy to the SLM, for admins to see (#10200).

Revision ID: 20261102_110
Revises: 20261102_109
Create Date: 2026-11-02 00:00:01.000000

``NO DATA LOSS``: two new nullable columns. Downgrade drops only those.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column

revision: str = "20261102_110"
down_revision: Union[str, None] = "20261102_109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_column("person_links", "push_failed_at"):
        op.add_column("person_links", sa.Column("push_failed_at", sa.DateTime(timezone=True), nullable=True))
    if not has_column("person_links", "push_error"):
        op.add_column("person_links", sa.Column("push_error", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("person_links", "push_error")
    op.drop_column("person_links", "push_failed_at")
