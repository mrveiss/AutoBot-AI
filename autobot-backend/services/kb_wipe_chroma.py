# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ChromaDB half of the approved knowledge wipe (#21048, #17038).

The KB's embeddings live in ChromaDB (``knowledge/base.py`` ``_init_vector_store``), not in Redis, so a
wipe that only flushed the ``knowledge`` Redis database would leave every vector behind. Only the KB's own
collections are cleared, by explicit name: the configured collection (``memory.chromadb.collection_name``)
and the collection of the active embedding space. The persist directory is never touched, other
collections (per-company KBs, memory) are never listed, and a collection is emptied rather than dropped so
a live KB's open handle stays valid.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from autobot_shared.embedding_model import active_embedding_space
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Ids deleted per call while emptying a collection.
CLEAR_BATCH = env_int_clamped("AUTOBOT_KB_WIPE_CHROMA_BATCH", 500, 1, 10000)

ChromaFactory = Callable[[], Awaitable[Any]]


def kb_collection_names() -> list[str]:
    """The KB's own collection names, deduplicated: configured first, then the active space's."""
    from config.manager import get_config_manager

    names = [get_config_manager().get("memory.chromadb.collection_name", "autobot_memory")]
    space = active_embedding_space()
    if space is not None and space.collection:
        names.append(space.collection)
    return list(dict.fromkeys(names))


async def default_chroma_client():
    """The same async client the KB uses, at the KB's configured persist path."""
    from config.manager import get_config_manager
    from knowledge.backends import get_async_default_client

    path = get_config_manager().get("memory.chromadb.path", "data/chromadb")
    return await get_async_default_client(db_path=str(path))


async def plan_chroma(client_factory: ChromaFactory | None = None) -> list[dict]:
    """Read only: each KB collection that exists, with its vector count."""
    client = await (client_factory or default_chroma_client)()
    plan = []
    for name in kb_collection_names():
        collection = await client.get_collection_or_none(name)
        if collection is not None:
            plan.append({"name": name, "vectors": int(await collection.count())})
    return plan


async def _empty(collection) -> None:
    while True:
        found = await collection.get(include=[], limit=CLEAR_BATCH)
        ids = found.get("ids") or []
        if not ids:
            return
        await collection.delete(ids=ids)


async def clear_chroma(client_factory: ChromaFactory | None = None) -> list[dict]:
    """Empty each existing KB collection; return what it held (name and vector count before)."""
    client = await (client_factory or default_chroma_client)()
    cleared = []
    for name in kb_collection_names():
        collection = await client.get_collection_or_none(name)
        if collection is None:
            continue
        before = int(await collection.count())
        await _empty(collection)
        cleared.append({"name": name, "vectors": before})
    return cleared
