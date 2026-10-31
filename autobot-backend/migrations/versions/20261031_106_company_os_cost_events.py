# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-event cost rows, each tied to the work item that incurred it (#16016).

Revision ID: 20261031_106
Revises: 20261030_105
Create Date: 2026-10-31 00:00:01.000000

``NO DATA LOSS``: one new table; nothing that exists is touched. ``llc_agent_budgets`` stays
the aggregate. ``work_item_id`` is nullable (a caller that does not know the item records
an unattributed cost) and ``ON DELETE SET NULL`` so deleting a work item keeps its spend.
Guarded with ``has_table`` for a database that ``create_all`` already built.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

revision: str = "20261031_106"
down_revision: Union[str, None] = "20261030_105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "company_os_cost_events"


def upgrade() -> None:
    if has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("work_item_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("tokens_in", sa.BigInteger, nullable=False),
        sa.Column("tokens_out", sa.BigInteger, nullable=False),
        sa.Column("cost", sa.Numeric(15, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["llc_work_items.id"], name="fk_company_os_cost_events_work_item", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_company_os_cost_events_company_id", TABLE, ["company_id"])
    op.create_index("ix_company_os_cost_events_work_item_id", TABLE, ["work_item_id"])


def downgrade() -> None:
    if not has_table(TABLE):
        return
    populated = op.get_bind().execute(sa.text("SELECT count(*) FROM company_os_cost_events")).scalar()
    if populated:
        raise NotImplementedError(
            f"20261031_106 downgrade is refused: {populated} cost event(s) exist. Dropping the table would "
            "discard them. Export and remove them first."
        )
    op.drop_table(TABLE)
