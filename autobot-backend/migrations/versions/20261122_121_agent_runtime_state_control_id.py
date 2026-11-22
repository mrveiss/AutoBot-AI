# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``agent_runtime_state.control_id``: one id per committed heartbeat control (#21376).

A pause, resume or terminate commits the row, then calls the scheduler; when that call fails the control
writes the prior values back, but only if the row still holds its own change. Status and actor repeat
across controls (pause, resume, pause again by the same person), so they cannot tell "my change" from a
newer identical one. Every control now writes a fresh ``control_id``, and the restore compares that.

``NO DATA REWRITE``: one nullable column is added; no existing row is read or changed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_table

revision: str = "20261122_121"
down_revision: Union[str, None] = "20261121_118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "agent_runtime_state"
_COLUMN = "control_id"


def upgrade() -> None:
    if has_table(_TABLE) and not has_column(_TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Uuid(as_uuid=True), nullable=True))


def downgrade() -> None:
    if has_table(_TABLE) and has_column(_TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
