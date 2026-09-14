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
facts are legacy. It marks every fact that, right now, has no owner and no visibility,
and logs how many there are. The startup backfill touches marked facts only. A fact
stored after deploy never carries the mark, so no caller can get one promoted at the
next restart by storing an ownerless fact whose metadata imitates an ingestion marker:
not the MCP add route, not the ``/extract`` auto-store, not an LLM's storefact tool.
New ingestion writes its visibility explicitly.

``NO DATA LOSS``: one metadata key is added to the matching rows, and nothing else
changes. ``downgrade`` removes exactly that key.
"""

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_table

revision: str = "20260914_092"
down_revision: Union[str, None] = "20260912_091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

# The key is knowledge.fact_store.BACKFILL_CANDIDATE_KEY; the migration gate cannot import it.
_MARK = sa.text(
    "UPDATE knowledge_facts"
    ' SET metadata_json = metadata_json || \'{"visibility_backfill_candidate": "16693"}\'::jsonb'
    " WHERE owner_id IS NULL AND (metadata_json ->> 'visibility') IS NULL"
)
_UNMARK = sa.text(
    "UPDATE knowledge_facts SET metadata_json = metadata_json - 'visibility_backfill_candidate'"
    " WHERE (metadata_json ->> 'visibility_backfill_candidate') IS NOT NULL"
)


def upgrade() -> None:
    if has_table("knowledge_facts"):
        marked = op.get_bind().execute(_MARK).rowcount
        logger.info("#16693: %d knowledge facts have no owner and no visibility; marked for the backfill", marked)


def downgrade() -> None:
    if has_table("knowledge_facts"):
        op.get_bind().execute(_UNMARK)
