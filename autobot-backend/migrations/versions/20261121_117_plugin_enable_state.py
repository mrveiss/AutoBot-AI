# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The operator's decision to let a plugin run in the backend process (#17421).

Revision ID: 20261121_117
Revises: 20261120_116
Create Date: 2026-11-21 00:00:00.000000

``NO DATA LOSS``: a new, empty table. Existing installs are grandfathered at the first start after
this revision, by the application, not here: only the host knows which plugins it was running.
Downgrade drops only that table, and with it the enable decisions and the ``__baseline__`` row: a later
re-upgrade grandfathers again at its first start (the plugins whose files predate the then-recorded
previous start, which is gone too, so every discovered plugin), and admin disables are forgotten.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

revision: str = "20261121_117"
down_revision: Union[str, None] = "20261120_116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("plugin_enable_state"):
        return
    op.create_table(
        "plugin_enable_state",
        sa.Column("plugin_name", sa.String(128), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    if has_table("plugin_enable_state"):
        op.drop_table("plugin_enable_state")
