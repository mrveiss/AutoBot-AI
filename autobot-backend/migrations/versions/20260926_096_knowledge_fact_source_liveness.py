# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Record whether a fact's source still resolves (#17545).

#17538 orders the retention work detect -> measure -> build, because the size of
the retention tier depends entirely on how often a source actually disappears
and nothing measured that. No fact recorded anything about its source's
liveness, so no query could name the facts that had lost their evidence.

Five columns, and the split between them is the point. ``source_checked_at``,
``source_seen_at``, ``source_last_probe`` and ``source_check_failures`` are
**observations** a probe wrote; ``source_gone_at`` is an **event** that was
witnessed by #17546's watchdog handlers and is never inferred from a probe. An
unmounted share answers ENOENT for every path beneath it, so "could not reach"
and "gone" must stay distinguishable or a retention sweep deletes documents that
were on disk the whole time.

``NO DATA LOSS``: five additive columns. Four are nullable with no default and
``source_check_failures`` defaults to 0, so every existing row backfills to
*never checked* -- which is true of all of them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column

revision: str = "20260926_096"
down_revision: Union[str, None] = "20260919_095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "knowledge_facts"

#: Column name -> definition. Ordered as the model declares them.
_COLUMNS = (
    ("source_checked_at", lambda: sa.Column("source_checked_at", sa.DateTime(timezone=True), nullable=True)),
    ("source_seen_at", lambda: sa.Column("source_seen_at", sa.DateTime(timezone=True), nullable=True)),
    ("source_last_probe", lambda: sa.Column("source_last_probe", sa.String(32), nullable=True)),
    (
        "source_check_failures",
        lambda: sa.Column("source_check_failures", sa.Integer(), nullable=False, server_default="0"),
    ),
    ("source_gone_at", lambda: sa.Column("source_gone_at", sa.DateTime(timezone=True), nullable=True)),
)


def upgrade() -> None:
    """Add the five liveness columns, skipping any that already exist."""
    for name, column in _COLUMNS:
        if not has_column(_TABLE, name):
            op.add_column(_TABLE, column())


def downgrade() -> None:
    """Drop exactly the five columns this migration added."""
    for name, _column in reversed(_COLUMNS):
        if has_column(_TABLE, name):
            op.drop_column(_TABLE, name)
