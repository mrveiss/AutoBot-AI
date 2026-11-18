# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ChromaDB half of the approved knowledge wipe (#21048, #17038).

The KB's embeddings live in ChromaDB (``knowledge/base.py`` ``_init_vector_store``), not in Redis, so a
wipe that only cleared Redis would leave every vector behind. Only the KB's own collections are cleared,
by explicit name: the configured collection (``memory.chromadb.collection_name``) and the collection of
the active embedding space. The persist directory is never touched, other collections (per-company KBs,
memory) are never listed, and a collection is emptied rather than dropped so a live KB's open handle
stays valid.

The names the wipe empties are the ones frozen in the approved plan (``frozen_collections``), checked against
the KB's current names BEFORE anything is deleted: the active space is read from Redis, so resolving it
afterwards would read a state the wipe had already changed.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from autobot_shared.embedding_model import read_embedding_space_strict
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Ids deleted per call while emptying a collection.
CLEAR_BATCH = env_int_clamped("AUTOBOT_KB_WIPE_CHROMA_BATCH", 500, 1, 10000)

ChromaFactory = Callable[[], Awaitable[Any]]


def kb_collection_names() -> list[str]:
    """The KB's own collection names, deduplicated: configured first, then the active space's.

    The active space is read strict and uncached: an unreadable store raises instead of silently dropping the
    active collection from the plan, and the validation at execution reads the same way.
    """
    from config.manager import get_config_manager

    names = [get_config_manager().get("memory.chromadb.collection_name", "autobot_memory")]
    space = read_embedding_space_strict()
    if space is not None and space.collection:
        names.append(space.collection)
    return list(dict.fromkeys(names))


def frozen_collections(plan_collections: list[dict], allowed: list[str]) -> list[str]:
    """The collection names the approved plan lists, each checked against *allowed*; raises on any other.

    The wipe empties exactly these. A name the KB does not own now (for example an embedding space that has
    since been switched) refuses the whole wipe before any delete: propose it again against the current state.
    """
    names = [item["name"] for item in plan_collections]
    outside = [name for name in names if name not in allowed]
    if outside:
        raise ValueError(f"the approved plan names collections the KB no longer owns ({outside}); nothing was deleted")
    return names


async def default_chroma_client():
    """The same async client the KB uses, at the KB's configured persist path."""
    from config.manager import get_config_manager
    from knowledge.backends import get_async_default_client

    path = get_config_manager().get("memory.chromadb.path", "data/chromadb")
    return await get_async_default_client(db_path=str(path))


async def plan_chroma(names: list[str], client_factory: ChromaFactory | None = None) -> list[dict]:
    """Read only: each named collection that exists, with its vector count."""
    client = await (client_factory or default_chroma_client)()
    plan = []
    for name in names:
        collection = await client.get_collection_or_none(name)
        if collection is not None:
            plan.append({"name": name, "vectors": int(await collection.count())})
    return plan


async def _empty(collection, entry: dict) -> None:
    """Empty *collection* batch by batch; ``entry["deleted"]`` counts the vectors removed so far."""
    while True:
        found = await collection.get(include=[], limit=CLEAR_BATCH)
        ids = found.get("ids") or []
        if not ids:
            return
        await collection.delete(ids=ids)
        entry["deleted"] += len(ids)


async def clear_chroma(names: list[str], record: list[dict], client_factory: ChromaFactory | None = None) -> None:
    """Empty each named collection that exists, recording into *record* as it goes.

    An entry is appended BEFORE its collection is emptied, with ``complete=False``, and flipped when
    the emptying finishes, and ``deleted`` grows per successful batch, so a failure mid-way still shows what was
    started and how many vectors were removed.
    """
    client = await (client_factory or default_chroma_client)()
    for name in names:
        collection = await client.get_collection_or_none(name)
        if collection is None:
            continue
        entry = {"name": name, "vectors": int(await collection.count()), "deleted": 0, "complete": False}
        record.append(entry)
        await _empty(collection, entry)
        entry["complete"] = True
