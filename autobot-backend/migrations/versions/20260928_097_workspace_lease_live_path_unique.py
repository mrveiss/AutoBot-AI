# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workspace path is unique among LIVE leases, not for all time (#16818).

Migration 093 created ``uq_llc_workspace_leases_path`` as a table-wide UNIQUE. The
model's own comment beside that column says what was meant:

    #: Unique: two *live* leases on one directory is the collision the ledger exists
    #: to prevent, so the database refuses it outright.

The comment says *live*; the constraint said *ever*. Under the table-wide version a
path can be leased exactly once in the lifetime of the installation -- the first
release permanently burns that directory, and the second acquire on it fails with an
integrity error. Since workspace paths are derived from issue numbers and are reused
constantly, that is every path, on its second use.

Nothing depended on the stricter reading: at 093 nothing acquired a lease at all, so
no deployment can hold a released row whose path is wanted again.

THE REPLACEMENT IS NOT EXACTLY ``is_live()``, AND CANNOT BE
------------------------------------------------------------
``LLCWorkspaceLease.is_live`` is ``released_at IS NULL AND expires_at > now``. This
index can only express the first half: a partial index predicate cannot call ``now()``,
because the index would have to be rebuilt continuously as rows aged across the
boundary. So the index permits a second live lease on a path whose existing lease has
**expired but not yet been released**.

That gap is closed by a convention, not by the schema: **every writer reclaims expired
leases before it inserts.** ``workspace_lease.acquire_lease`` does this as its first
statement, before it checks the path or counts capacity, and a test pins that ordering.
The index is exact only while that holds.

**The convention is necessary, not sufficient, and this paragraph used to imply it was**
(#17725 review). It closes the expired-but-unreleased case. It does not close the
concurrent-acquire race: two writers can both reclaim, both observe nothing live, and
both insert. No index predicate can close that one. It has to be handled in the service,
by serialising the acquire or by mapping the collision to ``WorkspaceLeaseHeld`` instead
of letting a raw integrity error escape. Tracked separately; this file documents the
dependency rather than claiming it is discharged.

Stated here rather than only in the service because this file is what the next person
writing an insert path will read when they wonder what the constraint guarantees. It
guarantees less than it looks like it does, and an insert that skips the reclaim can
collide with an expired row without the database objecting.

``NO DATA LOSS``: this drops a UNIQUE **constraint** and creates a weaker partial
unique index in its place. No column, table or row is touched -- every existing lease
row survives byte for byte, and the only thing removed is a restriction. A constraint
that is relaxed can lose nothing: every row that satisfied the table-wide UNIQUE also
satisfies the partial one, so no row can be rejected or dropped by the change.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision: str = "20260928_097"
down_revision: Union[str, None] = "20260926_096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "llc_workspace_leases"
_OLD_CONSTRAINT = "uq_llc_workspace_leases_path"
_NEW_INDEX = "uq_llc_workspace_leases_live_path"


def _has_table(bind) -> bool:
    return _TABLE in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(bind):
        return

    existing = {c["name"] for c in sa.inspect(bind).get_unique_constraints(_TABLE)}
    if _OLD_CONSTRAINT in existing:
        op.drop_constraint(_OLD_CONSTRAINT, _TABLE, type_="unique")

    indexes = {i["name"] for i in sa.inspect(bind).get_indexes(_TABLE)}
    if _NEW_INDEX not in indexes:
        op.create_index(
            _NEW_INDEX,
            _TABLE,
            ["path"],
            unique=True,
            postgresql_where=sa.text("released_at IS NULL"),
        )
    logger.info("#16818: workspace paths are now unique among live leases only")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not _has_table(bind):
        return

    indexes = {i["name"] for i in sa.inspect(bind).get_indexes(_TABLE)}
    if _NEW_INDEX in indexes:
        op.drop_index(_NEW_INDEX, table_name=_TABLE)

    # Restoring the table-wide UNIQUE can fail where a path has been leased more than
    # once -- which is the normal state after this migration has been in use. Left to
    # fail loudly rather than silently dropping the released rows that conflict: a
    # downgrade that destroys audit history to satisfy a constraint is worse than one
    # that stops and says why.
    existing = {c["name"] for c in sa.inspect(bind).get_unique_constraints(_TABLE)}
    if _OLD_CONSTRAINT not in existing:
        op.create_unique_constraint(_OLD_CONSTRAINT, _TABLE, ["path"])
