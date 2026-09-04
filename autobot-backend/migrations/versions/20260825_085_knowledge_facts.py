# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Give knowledge facts a durable system of record (#15663, #12733).

A fact has never been written anywhere that outlives Redis. #12733 is what that
costs: ``facts/by_category`` went 43 -> 0 while 22 ChromaDB vectors survived,
because the Redis hash was the only copy and RDB snapshots are a cache policy,
not a durability guarantee. This revision creates the table that makes the
``fact:<id>`` hash a projection rather than the original.

``NO DATA LOSS``: one new table. Nothing existing is altered, rewritten or
dropped, and no Redis key is touched -- the hashes keep serving reads while the
write path starts populating the rows beside them. Facts already in Redis are
backfilled by ``FactsMixin.rebuild_fact_projections(direction="from_redis")``,
which is a runtime repair rather than a migration step: it needs a Redis
connection, and the migration gate installs no autobot packages at all.

Guarded with ``has_table`` so a database already carrying this shape does not
hard-fail (the 20260812_073 idiom).

``downgrade`` drops exactly the table ``upgrade`` created. That discards the
durable copies -- unavoidable, since the table is where they live -- and leaves
the Redis hashes untouched, so a downgrade returns to the pre-revision state
rather than to an empty knowledge base.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260825_085"
down_revision: Union[str, None] = "20260824_084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written as a literal at every ``op.*`` call site below: migrations/baseline.py
# AST-extracts each revision's artifacts from literal arguments, and a constant
# would make this revision invisible to the probe ladder. Used only by the guard.
_TABLE = "knowledge_facts"


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _has_table(inspector, _TABLE):
        return

    op.create_table(
        "knowledge_facts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", JSONB(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("unique_key", sa.String(length=255), nullable=True),
        sa.Column("owner_id", sa.String(length=255), nullable=True),
        sa.Column("source_session_id", sa.String(length=255), nullable=True),
        # An observation of ChromaDB, never the authority for it (#15663 rule 3).
        sa.Column("vector_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_facts_content_hash", "knowledge_facts", ["content_hash"])
    op.create_index("ix_knowledge_facts_unique_key", "knowledge_facts", ["unique_key"])
    op.create_index("ix_knowledge_facts_owner_id", "knowledge_facts", ["owner_id"])
    op.create_index("ix_knowledge_facts_source_session_id", "knowledge_facts", ["source_session_id"])
    op.create_index("ix_knowledge_facts_owner_session", "knowledge_facts", ["owner_id", "source_session_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not _has_table(inspector, _TABLE):
        return
    op.drop_index("ix_knowledge_facts_owner_session", table_name="knowledge_facts")
    op.drop_index("ix_knowledge_facts_source_session_id", table_name="knowledge_facts")
    op.drop_index("ix_knowledge_facts_owner_id", table_name="knowledge_facts")
    op.drop_index("ix_knowledge_facts_unique_key", table_name="knowledge_facts")
    op.drop_index("ix_knowledge_facts_content_hash", table_name="knowledge_facts")
    op.drop_table("knowledge_facts")
