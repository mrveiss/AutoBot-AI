# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING chat-company-assignment proposal per chat, enforced by the database (#16905).

Two admins running the backfill proposer at once can both read "no pending proposal" and both insert one. A
partial unique index is the only thing that makes the second insert fail; the proposer maps that failure to
"already proposed".

``NO DATA REWRITE``: this adds an index only. No row or column is touched, and the index is partial, so it
constrains nothing except pending rows of this one requester and action. The proposer that creates those rows
ships in the same change, so no row exists that the index could reject.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261124_124"
down_revision: Union[str, None] = "20261124_123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_chat_company"
_WHERE = (
    "status = 'pending' AND requested_by_agent = 'chat-company-backfill' "
    "AND context ->> 'action' = 'chat_company_assignment'"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    op.create_index(
        _INDEX, _TABLE, [sa.text("(context ->> 'session_id')")], unique=True, postgresql_where=sa.text(_WHERE)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
