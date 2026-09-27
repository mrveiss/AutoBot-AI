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

#: Dropped in reverse order by `downgrade`. `upgrade` does NOT loop over this:
#: see its docstring -- the probe ladder reads the call site, not this tuple.
_COLUMN_NAMES = (
    "source_checked_at",
    "source_seen_at",
    "source_last_probe",
    "source_check_failures",
    "source_gone_at",
)


def upgrade() -> None:
    """Add the five liveness columns, skipping any that already exist.

    Written as five literal calls rather than a loop over a table of column
    definitions (#17125). The probe ladder extracts this revision's artifacts
    from the AST, and `baseline.extract_artifacts` records a column only when
    **both** `op.add_column`'s first argument is a string literal **and** its
    second is a `sa.Column(...)` whose first argument is one. The earlier form
    passed a `_TABLE` module constant and a `column()` factory, so the ladder
    extracted **nothing** from this revision: it became one of the
    "unobservable" revisions, which lets adoption bracket across it and stamp
    below a revision whose columns already exist.

    A module constant for the table name is better style and defeats the
    observer, which is the trade this file has to lose: the analysis reads
    source, not runtime. The marker route was available and refused --
    extending the allowlist would make this revision unobservable forever and
    make the next one easier to wave through, while five literals restore the
    observability for free.
    """
    if not has_column("knowledge_facts", "source_checked_at"):
        op.add_column("knowledge_facts", sa.Column("source_checked_at", sa.DateTime(timezone=True), nullable=True))
    if not has_column("knowledge_facts", "source_seen_at"):
        op.add_column("knowledge_facts", sa.Column("source_seen_at", sa.DateTime(timezone=True), nullable=True))
    if not has_column("knowledge_facts", "source_last_probe"):
        op.add_column("knowledge_facts", sa.Column("source_last_probe", sa.String(32), nullable=True))
    if not has_column("knowledge_facts", "source_check_failures"):
        op.add_column(
            "knowledge_facts",
            sa.Column("source_check_failures", sa.Integer(), nullable=False, server_default="0"),
        )
    if not has_column("knowledge_facts", "source_gone_at"):
        op.add_column("knowledge_facts", sa.Column("source_gone_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop exactly the five columns this migration added.

    A loop is fine here: `drop_column` is not extracted by the ladder, and the
    reverse order is the property that matters.
    """
    for name in reversed(_COLUMN_NAMES):
        if has_column("knowledge_facts", name):
            op.drop_column("knowledge_facts", name)
