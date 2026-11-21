# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING knowledge-base cleanup proposal per target (#20992, #17038).

The connector-credential strip (per connector) and the empty-collection delete (per collection) read for an
open proposal and then create one, so two requests can both create. A partial unique index per action is the
only thing that makes the second insert fail; the proposer reads that failure as "already proposed".

``NO DATA REWRITE``: this adds two partial indexes only. No row or column is touched, and each constrains
nothing except pending rows of its own action (none exist before the feature). If a dev install already
holds duplicate pending rows an index cannot be built over them, and the migration FAILS naming them. It
does not skip and it does not delete (no agent cleans data on its own, #17038). The fix is a person's:
reject the extra pending proposals in the Approvals inbox, then run the upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261121_117"
down_revision: Union[str, None] = "20261120_116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
#: (index name, context action, context key naming the target)
_INDEXES = (
    ("uq_approvals_pending_connector_credential_strip", "connector_credential_strip", "connector_id"),
    ("uq_approvals_pending_empty_collection_delete", "chroma_empty_collection_delete", "collection"),
)


def _where(action: str) -> str:
    return f"status = 'pending' AND context ->> 'action' = '{action}'"


_DUPLICATES_SQL = (
    "SELECT context ->> :key AS target, count(*) AS pending FROM approvals "
    "WHERE status = :status AND context ->> :action_key = :action "
    "GROUP BY 1 HAVING count(*) > 1 ORDER BY target LIMIT 20"
)


def _duplicates(bind, action: str, key: str) -> list:
    stmt = sa.text(_DUPLICATES_SQL).bindparams(key=key, status="pending", action_key="action", action=action)
    return bind.execute(stmt).all()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE):
        return
    for index, action, key in _INDEXES:
        if has_index(_TABLE, index):
            continue
        duplicates = _duplicates(bind, action, key)
        if duplicates:
            listed = ", ".join(f"{row.target} ({row.pending} pending)" for row in duplicates)
            raise RuntimeError(
                f"cannot create {index}: several pending {action} proposals exist for one target "
                f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the "
                "Approvals inbox so each keeps one, then run the upgrade again."
            )
        op.create_index(
            index, _TABLE, [sa.text(f"(context ->> '{key}')")], unique=True, postgresql_where=sa.text(_where(action))
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for index, _action, _key in _INDEXES:
        if has_index(_TABLE, index):
            op.drop_index(index, table_name=_TABLE)
