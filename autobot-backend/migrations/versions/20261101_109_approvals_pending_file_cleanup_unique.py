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
the index cannot be built over them: the migration logs that and skips, rather than deleting a
person's inbox rows. The proposer still handles the collision either way.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

logger = logging.getLogger(__name__)

revision: str = "20261101_109"
down_revision: Union[str, None] = "20261101_108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_file_cleanup"
_WHERE = (
    "status = 'pending' AND requested_by_agent = 'conversation-file-cleanup' "
    "AND context ->> 'action' = 'conversation_file_cleanup'"
)
_DUPLICATES = (
    "SELECT count(*) FROM (SELECT 1 FROM approvals "
    "WHERE status = 'pending' AND requested_by_agent = 'conversation-file-cleanup' "
    "AND context ->> 'action' = 'conversation_file_cleanup' "
    "GROUP BY context ->> 'file_id' HAVING count(*) > 1) d"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    duplicates = bind.execute(sa.text(_DUPLICATES)).scalar()
    if duplicates:
        logger.warning(
            "#20234: %d file(s) hold duplicate pending cleanup proposals; %s not created", duplicates, _INDEX
        )
        return
    op.create_index(_INDEX, _TABLE, [sa.text("(context ->> 'file_id')")], unique=True, postgresql_where=sa.text(_WHERE))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
