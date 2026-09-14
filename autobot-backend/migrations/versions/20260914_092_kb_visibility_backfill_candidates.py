# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Freeze the ownerless-fact visibility backfill's candidates at deploy time (#16693).

Owner decision on #16693: an ownerless fact that is an ingested document becomes SYSTEM,
and every other ownerless fact stays private. The classification and the writes run at
backend startup (``FactProjectionMixin.backfill_document_visibility``), because they need
Redis and ChromaDB, which the migration gate cannot reach.

This revision settles the one question that has to be answered at deploy time: which
facts are legacy. It adds ``knowledge_facts.visibility_backfill_candidate``, sets it on
every fact that right now has no owner and no visibility, and logs how many. The startup
backfill touches flagged facts only. A fact stored after deploy is never flagged, so no
caller can get one promoted at the next restart by storing an ownerless fact whose
metadata imitates an ingestion marker: not the MCP add route, not the ``/extract``
auto-store, not an LLM's storefact tool. New ingestion writes its visibility explicitly.

The flag is a column rather than a metadata key for two reasons. A column is a structural
marker, so baseline adoption observes this revision instead of re-running it. And the
flag is set only in the run that creates the column, so a re-run can never flag a fact
stored after the first deploy.

``NO DATA LOSS``: one nullable column is added and set on the matching rows, and nothing
else changes. ``downgrade`` drops exactly that column; the visibility the backfill wrote
stays.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_table

revision: str = "20260914_092"
down_revision: Union[str, None] = "20260912_091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_FLAG = sa.text(
    "UPDATE knowledge_facts SET visibility_backfill_candidate = TRUE"
    " WHERE owner_id IS NULL AND (metadata_json ->> 'visibility') IS NULL"
)


def upgrade() -> None:
    if not has_table("knowledge_facts") or has_column("knowledge_facts", "visibility_backfill_candidate"):
        return  # already applied: flagging again would take in facts stored since deploy
    op.add_column("knowledge_facts", sa.Column("visibility_backfill_candidate", sa.Boolean(), nullable=True))
    flagged = op.get_bind().execute(_FLAG).rowcount
    logger.info("#16693: %d knowledge facts have no owner and no visibility; flagged for the backfill", flagged)


def downgrade() -> None:
    if has_table("knowledge_facts") and has_column("knowledge_facts", "visibility_backfill_candidate"):
        op.drop_column("knowledge_facts", "visibility_backfill_candidate")
