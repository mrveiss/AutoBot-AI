# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One PENDING SSH-password deletion proposal per node, and one PENDING ``.env.*~`` cleanup per node (#20046, #20567).

Two requests can both read "no pending proposal" and both insert one. A partial unique index is the only
thing that makes the second insert fail; the routes map that failure to the existing proposal / 409.

``NO DATA REWRITE``: this adds indexes only. No row or column is touched, and both are partial, so they
constrain nothing except pending rows of their own action (none exist before these features). If a dev
install already holds duplicate pending rows an index cannot be built over them, and the migration FAILS
naming them. It does not skip (the index is the only thing that closes the race) and it does not delete (no
agent cleans data on its own, #17038). The fix is a person's: reject the extra pending proposals in the
Approvals inbox, then run the upgrade again.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_index, has_table

revision: str = "20261106_113"
down_revision: Union[str, None] = "20261105_111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "approvals"
_SSH_INDEX = "uq_approvals_pending_ssh_password_deletion"
_SSH_WHERE = "status = 'pending' AND context ->> 'action' = 'slm_node_ssh_password_delete'"  # pragma: allowlist secret
_ENV_INDEX = "uq_approvals_pending_env_copies_cleanup"
_ENV_WHERE = "status = 'pending' AND context ->> 'action' = 'env_backup_copies_cleanup'"
_SSH_DUPLICATES = (
    "SELECT context ->> 'node_id' AS key, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'slm_node_ssh_password_delete' "  # pragma: allowlist secret
    "GROUP BY context ->> 'node_id' HAVING count(*) > 1 ORDER BY key LIMIT 20"
)
_ENV_DUPLICATES = (
    "SELECT coalesce(context ->> 'node', '') AS key, count(*) AS pending FROM approvals "
    "WHERE status = 'pending' AND context ->> 'action' = 'env_backup_copies_cleanup' "
    "GROUP BY context ->> 'node' HAVING count(*) > 1 ORDER BY key LIMIT 20"
)


def _refuse_duplicates(bind, query: str, index: str, what: str) -> None:
    duplicates = bind.execute(sa.text(query)).all()
    if duplicates:
        listed = ", ".join(f"{row.key or '(no node)'} ({row.pending} pending)" for row in duplicates)
        raise RuntimeError(
            f"cannot create {index}: several pending {what} exist (first 20): {listed}. Nothing was changed. "
            "Reject the extra pending proposals in the Approvals inbox so each keeps one, then run the "
            "upgrade again."
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not has_table(_TABLE):
        return
    if not has_index(_TABLE, _SSH_INDEX):
        _refuse_duplicates(bind, _SSH_DUPLICATES, _SSH_INDEX, "SSH-password deletion proposals per node")
        op.create_index(
            _SSH_INDEX, _TABLE, [sa.text("(context ->> 'node_id')")], unique=True, postgresql_where=sa.text(_SSH_WHERE)
        )
    if not has_index(_TABLE, _ENV_INDEX):
        _refuse_duplicates(bind, _ENV_DUPLICATES, _ENV_INDEX, ".env.*~ cleanup proposals per node")
        op.create_index(
            _ENV_INDEX,
            _TABLE,
            [sa.text("(context ->> 'action')"), sa.text("(context ->> 'node')")],
            unique=True,
            postgresql_where=sa.text(_ENV_WHERE),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for index in (_ENV_INDEX, _SSH_INDEX):
        if has_index(_TABLE, index):
            op.drop_index(index, table_name=_TABLE)
