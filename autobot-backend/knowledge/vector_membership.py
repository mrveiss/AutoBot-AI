# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Whether a fact has a vector — asked of ChromaDB, never of a flag (#15663, #12733).

Rule 3 of the store-authority doctrine: derived status is computed, never stored
beside the data. Vectorisation status is the worked counter-example. It used to
live as ``vectorization_status`` / ``vectorized_at`` on the ``fact:<id>`` Redis
hash — a claim about ChromaDB's contents, written next to the fact, and wrong the
moment the two stores disagreed. #12733 is what that looks like from outside: the
facts were gone, their 22 vectors were not, and the browser reported everything
unvectorized on every reload.

One function, two callers. The status API answers the browser with it and the
background reconciler decides what to re-embed with it, so the two can no longer
disagree about what "vectorized" means.

:func:`vectorized_ids` returns ``None`` — not an empty set — when the vector
store cannot be reached. The distinction matters in both directions: a false
"nothing is vectorized" would make the browser lie, and would make the reconciler
re-embed the entire knowledge base.
"""

from __future__ import annotations

import asyncio
from typing import Iterable, Set

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def vectorized_ids(kb_instance, fact_ids: Iterable[str]) -> Set[str] | None:
    """Which of *fact_ids* ChromaDB actually holds a vector for.

    Args:
        kb_instance: KnowledgeBase carrying ``chromadb_path`` and
            ``chromadb_collection``.
        fact_ids: Fact ids to ask about.

    Returns:
        The subset ChromaDB holds, or ``None`` when the store is unreachable —
        which is a "don't know", and callers must treat it as one.
    """
    wanted = list(fact_ids)
    if not wanted:
        return set()
    try:
        from knowledge.backends import get_default_client

        client = await asyncio.to_thread(
            get_default_client,
            db_path=str(kb_instance.chromadb_path),
            allow_reset=False,
            anonymized_telemetry=False,
        )
        collection = await asyncio.to_thread(client.get_collection, kb_instance.chromadb_collection)
        found = await asyncio.to_thread(collection.get, ids=wanted, include=[])
        return set(found.get("ids") or [])
    except Exception as exc:  # noqa: BLE001 - status must degrade, never fail the caller
        logger.warning("Vector-store membership check unavailable: %s", exc)
        return None
