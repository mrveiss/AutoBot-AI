# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vectors in a knowledge backup: read them for export, put one back on restore (#19647).

Both sides go to the raw collection: the LlamaIndex store has neither get() nor upsert(). Chroma's
add() on an existing id keeps the old vector and raises nothing, so a restore looks first and reports
a skip rather than a write that did not happen. A wrong dimension makes Chroma raise, which the
restore reports as not restored.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from knowledge.embedding_space_binding import current_space
from knowledge.utils import sanitize_metadata_for_chromadb

logger = get_logger(__name__)

#: Facts read from the collection in one call while exporting their vectors.
EXPORT_BATCH_SIZE = env_int_clamped("AUTOBOT_KB_BACKUP_EMBEDDING_BATCH_SIZE", 500, 1, 5000)


async def fetch_backup_embeddings(kb, fact_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Each fact's vector and the model its own metadata names, read in batches."""
    space = await current_space(kb)
    fetched: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(fact_ids), EXPORT_BATCH_SIZE):
        batch = fact_ids[start : start + EXPORT_BATCH_SIZE]
        result = await asyncio.to_thread(
            space.vector_store._collection.get, ids=batch, include=["embeddings", "metadatas"]
        )
        for fact_id, vector, metadata in zip(result["ids"], result["embeddings"], result["metadatas"]):
            fetched[fact_id] = {
                "embedding": [float(v) for v in vector],  # numpy from Chroma: not JSON-serializable
                "embedding_model": (metadata or {}).get("embedding_model"),
            }
    return fetched


async def restore_backup_embedding(kb, fact_id: str, fact_data: Dict[str, Any]) -> Dict[str, Any]:
    """A backup's vector only if the bound model made it and the fact has none yet.

    #13708: content and metadata are what store_fact persisted, never the backup's raw copy.
    """
    not_restored = {"action": "restored", "embedding": False}
    try:
        space = await current_space(kb)
        if fact_data.get("embedding_model") != space.model:
            return not_restored
        existing = await asyncio.to_thread(space.vector_store._collection.get, ids=[fact_id], include=[])
        if existing["ids"]:
            return not_restored  # store_fact embedded it with the bound model, and add() would change nothing
        fact = await kb._get_fact_for_vectorization(fact_id)
        if not fact or "error" in fact:
            return not_restored
        metadata = sanitize_metadata_for_chromadb(fact["metadata"])
        if not await kb._write_vector(space, fact_id, fact_data["embedding"], fact["content"], metadata, ""):
            return not_restored
        await kb._mark_vectorization_succeeded(fact_id)
        return {"action": "restored", "embedding": True}
    except Exception as e:
        logger.warning("Embedding restore failed: %s", e)
        return not_restored
