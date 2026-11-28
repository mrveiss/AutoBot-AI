# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING conversation-file-cleanup proposal per file, enforced by the database (#20234).

A delete and a startup sweep on different workers can both read "no pending proposal" and both
insert one. A partial unique index is the only thing that makes the second insert fail; the
proposer maps that failure to "already proposed".

``NO DATA REWRITE``: this adds an index only. No row or column is touched, and the index is partial,
so it constrains nothing except pending rows of this one requester and action (the rows the cleanup
proposer creates; none exist before #20234). If a dev install already holds duplicate pending rows
the index cannot be built over them, and the migration FAILS with a message naming the files. It does
not skip (the index is the only thing that closes the race, and a skipped one is an invariant nobody
sees missing) and it does not delete (no agent cleans data on its own, #17038). The fix is a person's:
reject the extra pending proposals in the Approvals inbox, then run the upgrade again. Only dev installs
can hold duplicates, since the proposer that creates these rows ships in the same change.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261101_110"
down_revision: Union[str, None] = "20261101_109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_file_cleanup"
_WHERE = (
    "status = 'pending' AND requested_by_agent = 'conversation-file-cleanup' "
    "AND context ->> 'action' = 'conversation_file_cleanup'"
)
_DUPLICATES = (
    "SELECT context ->> 'file_id' AS file_id, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND requested_by_agent = 'conversation-file-cleanup' "
    "AND context ->> 'action' = 'conversation_file_cleanup' "
    "GROUP BY context ->> 'file_id' HAVING count(*) > 1 ORDER BY file_id LIMIT 20"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = bind.execute(sa.text(_DUPLICATES)).all()
    if duplicates:
        listed = ", ".join(f"{row.file_id} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"#20234: cannot create {_INDEX}: these conversation files hold several pending cleanup proposals "
            f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the Approvals "
            "inbox so each file keeps one, then run the upgrade again."
        )
    op.create_index(_INDEX, _TABLE, [sa.text("(context ->> 'file_id')")], unique=True, postgresql_where=sa.text(_WHERE))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
