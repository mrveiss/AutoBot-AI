# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING workflow-grant subject remap proposal per scope (#22180, #17038).

The remap proposer reads for an open proposal and then creates one, so two concurrent admin requests can both
create. A partial unique index is the only thing that makes the second insert fail; the proposer reads that
failure as "already proposed".

``NO DATA REWRITE``: this adds one partial index only. No row or column is touched, and it constrains nothing
except pending rows of its own action (none exist before the feature). If an install already holds duplicate
pending rows an index cannot be built over them, and the migration FAILS naming them. It does not skip and it
does not delete (no agent cleans data on its own, #17038). The fix is a person's: reject the extra pending
proposals in the Approvals inbox, then run the upgrade again.

Chain note: open PR #22195 adds ``20261124_123`` on the same parent (``20261122_122``). Whichever lands second
re-points its ``down_revision`` at the other so the chain keeps a single head.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261124_124"
down_revision: Union[str, None] = "20261122_122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_workflow_grant_remap"
_ACTION = "workflow_grant_subject_remap"
_KEY = "scope"


def _where(action: str) -> str:
    return f"status = 'pending' AND context ->> 'action' = '{action}'"


_DUPLICATES_SQL = (
    "SELECT context ->> :key AS target, count(*) AS pending FROM approvals "
    "WHERE status = :status AND context ->> :action_key = :action "
    "GROUP BY 1 HAVING count(*) > 1 ORDER BY target LIMIT 20"
)


def _duplicates(bind) -> list:
    stmt = sa.text(_DUPLICATES_SQL).bindparams(key=_KEY, status="pending", action_key="action", action=_ACTION)
    return bind.execute(stmt).all()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = _duplicates(bind)
    if duplicates:
        listed = ", ".join(f"{row.target} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"cannot create {_INDEX}: several pending {_ACTION} proposals exist for one scope "
            f"(first 20): {listed}. Nothing was changed. Reject the extra pending proposals in the "
            "Approvals inbox so each keeps one, then run the upgrade again."
        )
    op.create_index(
        _INDEX, _TABLE, [sa.text(f"(context ->> '{_KEY}')")], unique=True, postgresql_where=sa.text(_where(_ACTION))
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
