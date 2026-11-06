# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING ``.env.*~`` cleanup proposal at a time, enforced by the database (#20567).

Two admins can both read "no pending proposal" and both insert one. A partial unique index is the
only thing that makes the second insert fail; the route maps that failure to 409.

``NO DATA REWRITE``: this adds an index only. No row or column is touched, and the index is partial,
so it constrains nothing except pending rows of the ``env_backup_copies_cleanup`` action (none exist
before #20567). If a dev install already holds several pending rows the index cannot be built over
them, and the migration FAILS with a message giving the count. It does not skip (the index is the
only thing that closes the race) and it does not delete (no agent cleans data on its own, #17038).
The fix is a person's: reject the extra pending proposals in the Approvals inbox, then run the
upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261106_112"
down_revision: Union[str, None] = "20261105_111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_INDEX = "uq_approvals_pending_env_copies_cleanup"
_WHERE = "status = 'pending' AND context ->> 'action' = 'env_backup_copies_cleanup'"
_PENDING = (
    "SELECT count(*) FROM approvals WHERE status = 'pending' AND context ->> 'action' = 'env_backup_copies_cleanup'"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE) or has_index(_TABLE, _INDEX):
        return
    pending = bind.execute(sa.text(_PENDING)).scalar() or 0
    if pending > 1:
        raise RuntimeError(
            f"#20567: cannot create {_INDEX}: {pending} pending .env.*~ cleanup proposals exist. Nothing was "
            "changed. Reject the extra pending proposals in the Approvals inbox so one remains, then run "
            "the upgrade again."
        )
    op.create_index(_INDEX, _TABLE, [sa.text("(context ->> 'action')")], unique=True, postgresql_where=sa.text(_WHERE))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and has_index(_TABLE, _INDEX):
        op.drop_index(_INDEX, table_name=_TABLE)
