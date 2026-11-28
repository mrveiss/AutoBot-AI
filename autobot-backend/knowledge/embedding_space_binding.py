# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Keep a knowledge-base process bound to the active embedding space (#19379).

The KB's collection is several objects: the raw collection, the LlamaIndex vector store over it,
the write buffer whose flush closes over that store, the lazy vector index, and the model its
vectors were made with. A switch writes one record (model + collection + generation,
``autobot_shared.embedding_model``); each process -- every uvicorn worker and Celery -- notices a
newer generation and rebinds.

Two rules keep a query from pairing one model with another model's vectors:

- **One source for the model.** Search and the write path embed with the model of the space the
  KB is bound to (``current_space``), never with ``active_embedding_model()`` directly: the record
  and the KB's binding are read through different caches, and only the binding names the
  collection the vector will meet.
- **One swap.** A rebind builds the new collection, store and buffer off to the side, then assigns
  every bound attribute in one synchronous block -- no ``await`` inside it, so no coroutine sees a
  half-swapped KB -- and only then drains the old buffer into the old store. An operation takes one
  snapshot (``current_space``) and uses it for both embedding and the store it writes or queries.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from autobot_shared.embedding_model import EmbeddingSpace, active_embedding_model, active_embedding_space
from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: How often a process re-reads the record to notice a switch made elsewhere.
SPACE_CHECK_INTERVAL_S = env_float_clamped("AUTOBOT_EMBEDDING_SPACE_CHECK_SECONDS", 5.0, 0.0, 300.0)


@dataclass(frozen=True)
class BoundSpace:
    """What one KB operation uses, read in one synchronous step: the model and its store."""

    model: str
    collection: str
    generation: int
    vector_store: Any
    write_buffer: Any


def initial_collection(kb, configured: str) -> str:
    """The collection a KB binds at init: a switched space's, else the configured one."""
    space = active_embedding_space()
    kb._bound_generation = space.generation if space is not None and space.collection else 0
    kb._space_checked_at = time.monotonic()
    return space.collection if space is not None and space.collection else configured


def snapshot(kb) -> BoundSpace:
    """The KB's bound space, read without an await so it cannot straddle a rebind."""
    model = getattr(kb, "embedding_model_name", None) or active_embedding_model()
    return BoundSpace(
        model=model,
        collection=getattr(kb, "chromadb_collection", ""),
        generation=getattr(kb, "_bound_generation", 0),
        vector_store=getattr(kb, "vector_store", None),
        write_buffer=getattr(kb, "_write_buffer", None),
    )


async def current_space(kb) -> BoundSpace:
    """Rebind first if another process cut over, then one snapshot for the whole operation."""
    await ensure_current_space(kb)
    return snapshot(kb)


async def ensure_current_space(kb) -> bool:
    """Rebind *kb* if another process cut over to a newer space; True when it rebound."""
    now = time.monotonic()
    if now - getattr(kb, "_space_checked_at", 0.0) < SPACE_CHECK_INTERVAL_S:
        return False
    kb._space_checked_at = now
    # a blocking Redis GET when the override cache has expired: off the event loop
    space = await asyncio.to_thread(active_embedding_space)
    if space is None or not space.collection or space.generation <= getattr(kb, "_bound_generation", 0):
        return False
    try:
        await rebind(kb, space)
    except Exception as exc:  # noqa: BLE001 - keep serving from the bound space; retried next interval
        logger.error("Rebind to embedding space %s (generation %d) failed: %s", space.collection, space.generation, exc)
        return False
    return True


async def build_binding(kb, client, collection: str, metadata: dict):
    """The collection, its LlamaIndex store and a write buffer over it, built without touching *kb*.

    The one place these are made: KB init (``_create_chroma_collection``) and every rebind.
    """
    from llama_index.vector_stores.chroma import ChromaVectorStore

    from knowledge.write_buffer import VectorWriteBuffer, make_chromadb_flush_fn

    abc_collection = await asyncio.to_thread(client.get_or_create_collection, name=collection, metadata=metadata)
    store = ChromaVectorStore(chroma_collection=getattr(abc_collection, "_raw", abc_collection))

    async def _on_flush_error(count: int, exc: Exception) -> None:
        # Issue #8406: a dropped batch corrects the optimistic total_vectors increment.
        logger.error("VectorWriteBuffer flush lost %d vectors; decrementing total_vectors: %s", count, exc)
        await kb._decrement_stat("total_vectors", count)

    buffer = VectorWriteBuffer(flush_fn=make_chromadb_flush_fn(store), on_flush_error=_on_flush_error)
    return abc_collection, store, buffer


def _lock(kb) -> asyncio.Lock:
    """One rebind at a time per KB, made inside the loop that uses it."""
    lock = kb.__dict__.get("_rebind_lock")
    if lock is None:
        lock = kb.__dict__["_rebind_lock"] = asyncio.Lock()
    return lock


async def rebind(kb, space: EmbeddingSpace) -> None:
    """Point *kb* at *space*'s collection and model in one swap, then drain the old buffer."""
    async with _lock(kb):
        if space.generation <= getattr(kb, "_bound_generation", 0):
            return
        from knowledge.backends import get_default_client

        client = await asyncio.to_thread(
            get_default_client, db_path=str(kb.chromadb_path), allow_reset=False, anonymized_telemetry=False
        )
        abc, store, buffer = await build_binding(kb, client, space.collection, kb._build_hnsw_metadata())
        old_buffer = getattr(kb, "_write_buffer", None)
        if old_buffer is not None:
            await buffer.start()
        try:
            _swap(kb, space, abc, store, buffer)  # synchronous: nothing sees a half-swapped KB
        except Exception:
            if old_buffer is not None:
                await buffer.stop()  # the KB kept its old binding; do not leave this buffer's task running
            raise
    if old_buffer is not None:
        await old_buffer.stop()  # flushes what was queued into the collection it was made for
    logger.warning(
        "Knowledge base rebound to embedding space %s in %s (generation %d, #19379)",
        space.model,
        space.collection,
        space.generation,
    )


def _swap(kb, space: EmbeddingSpace, abc, store, buffer) -> None:
    from autobot_shared.ssot_config import config as ssot_config

    provider = ssot_config.llm.llamaindex_embedding_provider.lower()
    dims = kb._configure_embedding_provider(
        provider, space.model, ssot_config.llm.llamaindex_embedding_endpoint, ssot_config
    )
    kb._async_chroma_collection, kb.vector_store, kb._write_buffer = abc, store, buffer
    kb.chromadb_collection, kb.vector_index = space.collection, None
    kb.embedding_model_name, kb.embedding_dimensions = space.model, dims
    kb._bound_generation = space.generation
