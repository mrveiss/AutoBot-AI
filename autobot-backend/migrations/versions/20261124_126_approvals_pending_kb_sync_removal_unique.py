# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING knowledge-sync removal proposal per scope (#20028, #17038).

The sync proposes removals on every run, so two runs can both pass the "already proposed" read. A partial
unique index on the proposal's ``scope`` (kind, project root and fact batch) is the only thing that makes the
second insert fail; the proposer reads that failure as "already proposed".

Chain: this revision descends from ``20261124_125`` (#22225), which follows ``20261124_124`` (#22176), which
follows ``20261124_123`` (stale code-sync files, #22033, main's head). A single head is required, so this one
is re-parented whenever the revisions before it change.

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

revision: str = "20261124_126"
down_revision: Union[str, None] = "20261124_125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_kb_sync_removal"
_ACTION = "kb_sync_removal"
_WHERE = f"status = 'pending' AND context ->> 'action' = '{_ACTION}'"
_DUPLICATES_SQL = (
    "SELECT context ->> 'scope' AS target, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'kb_sync_removal' "
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
            f"cannot create {_INDEX}: several pending {_ACTION} proposals exist for one scope "
            f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the "
            "Approvals inbox so each keeps one, then run the upgrade again."
        )
    op.create_index(_INDEX, _TABLE, [sa.text("(context ->> 'scope')")], unique=True, postgresql_where=sa.text(_WHERE))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
