# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING internal-key realign proposal per node (#20750).

Two updater requests can both read "no pending proposal" and both insert one. A partial unique index is the
only thing that makes the second insert fail; the propose route maps that failure to the existing proposal.
Migration 20261106_113 built the same guard for SSH-password deletions only.

``NO DATA REWRITE``: this adds one partial index only. No row or column is touched, and it constrains nothing
except pending rows of its own action. If an install already holds duplicate pending realign rows an index
cannot be built over them, and the migration FAILS naming them. It does not skip (the index is the only thing
that closes the race) and it does not delete (no agent cleans data on its own, #17038). The fix is a
person's: reject the extra pending proposals in the Approvals inbox, then run the upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261107_114"
down_revision: Union[str, None] = "20261106_113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_key_realign"
_WHERE = "status = 'pending' AND context ->> 'action' = 'slm_backend_internal_key_realign'"
_DUPLICATES = (
    "SELECT context ->> 'node_id' AS key, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'slm_backend_internal_key_realign' "
    "GROUP BY context ->> 'node_id' HAVING count(*) > 1 ORDER BY key LIMIT 20"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = bind.execute(sa.text(_DUPLICATES)).all()
    if duplicates:
        listed = ", ".join(f"{row.key or '(no node)'} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"cannot create {_INDEX}: several pending key-realign proposals exist (first 20): {listed}. "
            "Nothing was changed. Reject the extra pending proposals in the Approvals inbox so each keeps "
            "one, then run the upgrade again."
        )
    op.create_index(_INDEX, _TABLE, [sa.text("(context ->> 'node_id')")], unique=True, postgresql_where=sa.text(_WHERE))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
