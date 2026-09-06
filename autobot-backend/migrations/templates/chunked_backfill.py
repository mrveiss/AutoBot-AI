# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Template: backfill a column in bounded chunks (#15776).

Not a migration. It lives outside ``migrations/versions/`` so alembic never
loads it -- copy the body into a real revision.

An unbounded ``UPDATE`` over a large table holds locks for the length of the
update and can exceed the database's bind-parameter limit; a migration that
cannot finish stops a rolling update mid-flight, which is the failure this
template exists to avoid.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from autobot_shared.env_utils import env_int_clamped

#: Rows per statement. An env-var-backed module constant rather than a literal,
#: per the repository's no-hardcoding rule -- the right size depends on row
#: width and on the database, neither of which is knowable here.
BACKFILL_BATCH_SIZE = env_int_clamped("AUTOBOT_MIGRATION_BACKFILL_BATCH_SIZE", 1000, min_v=1, max_v=50_000)


def backfill_in_chunks(table: str, key: str, set_clause: str, where: str = "TRUE") -> int:
    """Apply *set_clause* to every matching row, ``BACKFILL_BATCH_SIZE`` at a time.

    Returns the number of rows touched. Progresses by primary key rather than by
    ``LIMIT`` alone, so a row updated in one batch cannot be re-selected by the
    next and the walk terminates.
    """
    connection = op.get_bind()
    last_key: object = None
    touched = 0
    while True:
        cursor = connection.execute(
            sa.text(
                f"SELECT {key} FROM {table} "  # nosec B608  # identifiers are migration-authored, not user input
                f"WHERE {where} AND (:last_key IS NULL OR {key} > :last_key) "
                f"ORDER BY {key} LIMIT :batch"
            ),
            {"last_key": last_key, "batch": BACKFILL_BATCH_SIZE},
        )
        keys = [row[0] for row in cursor]
        if not keys:
            return touched
        connection.execute(
            sa.text(
                f"UPDATE {table} SET {set_clause} "  # nosec B608  # see above
                f"WHERE {key} IN :keys"
            ).bindparams(
                sa.bindparam("keys", expanding=True)
            ),
            {"keys": keys},
        )
        touched += len(keys)
        last_key = keys[-1]
