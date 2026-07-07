# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""llc project code_source link (#11129)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_066"
down_revision: Union[str, None] = "20260630_065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llc_projects", sa.Column("code_source_id", sa.String(length=64), nullable=True))
    op.create_index("ix_llc_projects_code_source_id", "llc_projects", ["code_source_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_projects_code_source_id", table_name="llc_projects")
    op.drop_column("llc_projects", "code_source_id")
