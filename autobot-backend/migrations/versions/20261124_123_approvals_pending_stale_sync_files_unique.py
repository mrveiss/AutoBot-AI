# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING stale code-sync file cleanup proposal per old sync location per node (#22033, #17038).

The SLM's propose call reads for an open proposal and then creates one, so two requests can both create. A
partial unique index is the only thing that makes the second insert fail; the route reads that failure as
"already proposed".

Chain: this revision descends from ``20261122_122`` (the audit chain, #17219), which was main's head when this
landed; a single head is required.

``NO DATA REWRITE``: this adds one partial index only. No row or column is touched, and it constrains
nothing except pending rows of its own action (none exist before the feature). If a dev install already
holds duplicate pending rows an index cannot be built over them, and the migration FAILS naming them. It
does not skip and it does not delete (no agent cleans data on its own, #17038). The fix is a person's:
reject the extra pending proposals in the Approvals inbox, then run the upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261124_123"
down_revision: Union[str, None] = "20261122_122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_stale_sync_files_cleanup"
_ACTION = "slm_node_stale_sync_files_cleanup"
_WHERE = f"status = 'pending' AND context ->> 'action' = '{_ACTION}'"
_DUPLICATES_SQL = (
    "SELECT context ->> 'location' AS target, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'slm_node_stale_sync_files_cleanup' "
    "GROUP BY 1 HAVING count(*) > 1 ORDER BY target LIMIT 20"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = bind.execute(sa.text(_DUPLICATES_SQL)).all()
    if duplicates:
        listed = ", ".join(f"{row.target} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"cannot create {_INDEX}: several pending {_ACTION} proposals exist for one location "
            f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the "
            "Approvals inbox so each keeps one, then run the upgrade again."
        )
    op.create_index(
        _INDEX, _TABLE, [sa.text("(context ->> 'location')")], unique=True, postgresql_where=sa.text(_WHERE)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
