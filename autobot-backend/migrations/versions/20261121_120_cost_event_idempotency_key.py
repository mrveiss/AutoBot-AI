# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cost event can carry the idempotency key it was charged under (#21972, part of #21332).

Revision ID: 20261121_120
Revises: 20261120_117
Create Date: 2026-11-21 00:00:01.000000

``NO DATA LOSS``: adds one nullable column and one partial unique index over (company_id, agent_id,
idempotency_key). Existing rows have no key, so the index (``WHERE idempotency_key IS NOT NULL``) cannot reject
any of them. The charge writes the keyed row in its own transaction before it changes spend, so only the
transaction that inserted the row may charge; a repeat replays the stored cost.

``downgrade`` drops the index only. The nullable column stays: dropping it would delete the recorded keys, and
a column nothing constrains is harmless.

Open PRs also claim 20261121_118 and 20261121_119; re-parent ``down_revision`` onto whichever of them lands first.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_index, has_table

revision: str = "20261121_120"
down_revision: Union[str, None] = "20261120_117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "company_os_cost_events"
INDEX = "uq_company_os_cost_events_idempotency"


def upgrade() -> None:
    if not has_table(TABLE):
        return  # create_all builds the table with the column and index
    if not has_column(TABLE, "idempotency_key"):
        op.add_column("company_os_cost_events", sa.Column("idempotency_key", sa.String(255), nullable=True))
    if not has_index(TABLE, INDEX):
        op.create_index(
            "uq_company_os_cost_events_idempotency",
            "company_os_cost_events",
            ["company_id", "agent_id", "idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    if has_index(TABLE, INDEX):
        op.drop_index("uq_company_os_cost_events_idempotency", table_name="company_os_cost_events")
