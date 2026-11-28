# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING chat-session owner proposal per session, enforced by the database (#20030).

Two admins can both read "no pending proposal" and both insert one. A partial unique index is the
only thing that makes the second insert fail; the route maps that failure to 409.

``NO DATA REWRITE``: this adds an index only. No row or column is touched, and the index is partial,
so it constrains nothing except pending rows of the ``chat_session_owner_assign`` action (none exist
before #20030). If a dev install already holds duplicate pending rows the index cannot be built over
them, and the migration FAILS with a message naming the sessions. It does not skip (the index is the
only thing that closes the race) and it does not delete (no agent cleans data on its own, #17038). The
fix is a person's: reject the extra pending proposals in the Approvals inbox, then run the upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261105_111"
down_revision: Union[str, None] = "20261101_110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_chat_session_owner"
_WHERE = "status = 'pending' AND context ->> 'action' = 'chat_session_owner_assign'"
_DUPLICATES = (
    "SELECT context ->> 'session_id' AS session_id, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'chat_session_owner_assign' "
    "GROUP BY context ->> 'session_id' HAVING count(*) > 1 ORDER BY session_id LIMIT 20"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = bind.execute(sa.text(_DUPLICATES)).all()
    if duplicates:
        listed = ", ".join(f"{row.session_id} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"#20030: cannot create {_INDEX}: these chat sessions hold several pending owner proposals "
            f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the Approvals "
            "inbox so each session keeps one, then run the upgrade again."
        )
    op.create_index(
        _INDEX, _TABLE, [sa.text("(context ->> 'session_id')")], unique=True, postgresql_where=sa.text(_WHERE)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
