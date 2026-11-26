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
down_revision: Union[str, None] = "20261121_120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Literal names: the probe ladder reads the table and column from this call (test_probe_ladder_selfcheck).
    if has_table("agent_runtime_state") and not has_column("agent_runtime_state", "control_id"):
        op.add_column("agent_runtime_state", sa.Column("control_id", sa.Uuid(as_uuid=True), nullable=True))


def downgrade() -> None:
    if has_table("agent_runtime_state") and has_column("agent_runtime_state", "control_id"):
        op.drop_column("agent_runtime_state", "control_id")
