# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The one hook that keeps RAG caches honest over KB writes (#20958).

``semantic_query_cache`` (tier 0), the in-process exact cache (tier 1) and ``topic_retrieval_cache``
(tier 2) all key every entry on a visibility scope that embeds the KB epoch
(``services.rag_visibility.scope_key`` <- ``knowledge.acl_epoch``). Replacing the epoch therefore
orphans every cached result of every tier at once, in every process, with no per-cache plumbing;
this module reuses that mechanism instead of adding a second one.

Scope choice: the caches are partitioned by principal scope, not by collection, so a per-collection
invalidation has nothing to key on. A write replaces the single epoch (a full clear). Orphaned
entries are never read again and leave on their own TTL / size eviction.

A write entry point opts in with ``@invalidates_retrieval_caches(reason)``. The decorator fires in a
``finally``: a write that failed half-way may still have changed what a search returns. A failed
bump is logged at error level and not raised: the write is already durable, and an unreadable epoch
makes every cache tier skip itself (``cache_scope`` returns ``None``), so no stale entry is served.

``WRITE_ENTRY_POINTS`` is the single enumeration of those entry points; the guard test
(``retrieval_invalidation_20958_test.py``) fails when a registered function lost its decorator, a
decorated function is unregistered, or a vector write appears outside the registry.
"""

import functools
import inspect
from typing import Any, Awaitable, Callable, NamedTuple, TypeVar

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from knowledge.acl_epoch import ACL_EPOCH_DATABASE, bump_acl_epoch_async

logger = get_logger(__name__)

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


class WriteEntryPoint(NamedTuple):
    """A KB write that changes what retrieval can return: file (under autobot-backend), function, reason."""

    path: str
    qualname: str
    reason: str


#: The composed KB class; its fact and collection writes are wrapped by ``@invalidating_writes`` (those
#: mixin files are grandfathered at a fixed size, so the wrapping lives at the composition point).
COMPOSED = "knowledge/_composed.py"

#: Every KB write entry point. Trust changes, quarantine, unquarantine, promotion and rejection are
#: metadata updates and so enter through ``FactsMixin.update_fact``.
WRITE_ENTRY_POINTS: tuple[WriteEntryPoint, ...] = (
    WriteEntryPoint(COMPOSED, "KnowledgeBase.store_fact", "fact_added"),
    WriteEntryPoint(COMPOSED, "KnowledgeBase.update_fact", "fact_updated"),
    WriteEntryPoint(COMPOSED, "KnowledgeBase.delete_fact", "fact_deleted"),
    WriteEntryPoint(COMPOSED, "KnowledgeBase.delete_facts_by_session", "session_facts_deleted"),
    WriteEntryPoint(COMPOSED, "KnowledgeBase.delete_collection", "collection_deleted"),
    WriteEntryPoint(COMPOSED, "KnowledgeBase.bulk_delete_collection_facts", "collection_facts_deleted"),
    WriteEntryPoint("knowledge/write_buffer.py", "make_chromadb_flush_fn._flush", "vectors_flushed"),
    WriteEntryPoint("services/knowledge/doc_index_orphans.py", "reindex_file", "doc_indexed"),
    WriteEntryPoint("services/knowledge/doc_index_orphans.py", "drop_collection", "docs_collection_dropped"),
    WriteEntryPoint("services/knowledge/kb_synthesizer.py", "KBSynthesizer._index_documents", "synthesis_indexed"),
)


async def invalidate_retrieval_caches(reason: str) -> bool:
    """Orphan every cached retrieval result by replacing the KB epoch; ``False`` when that failed."""
    try:
        client = await get_async_redis_client(database=ACL_EPOCH_DATABASE)
        await bump_acl_epoch_async(client)
    except Exception as exc:
        logger.error("Retrieval caches NOT invalidated after %s: %s", reason, exc)
        return False
    logger.debug("Retrieval caches invalidated: %s", reason)
    return True


def invalidates_retrieval_caches(reason: str) -> Callable[[_F], _F]:
    """Decorate an async KB write so the retrieval caches are invalidated once it ends (see module doc)."""

    def decorate(fn: _F) -> _F:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@invalidates_retrieval_caches needs an async function, got {fn.__qualname__}")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            finally:
                await invalidate_retrieval_caches(reason)

        return wrapper  # type: ignore[return-value]

    return decorate


def invalidating_writes(cls: type) -> type:
    """Class decorator: wrap each ``WRITE_ENTRY_POINTS`` method named on *cls* with the hook."""
    for entry in WRITE_ENTRY_POINTS:
        owner, _, name = entry.qualname.rpartition(".")
        if owner == cls.__name__:
            setattr(cls, name, invalidates_retrieval_caches(entry.reason)(getattr(cls, name)))
    return cls
