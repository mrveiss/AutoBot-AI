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
bump is not raised: the write is already durable. When the epoch is unreadable every cache tier
skips itself (``cache_scope`` returns ``None``). When only the SET is rejected (a read-only or
degraded Redis) the old epoch stays readable, so the failed bump also marks this process
"invalidation pending": ``invalidation_pending`` makes ``cache_scope`` return ``None`` (read and
write bypass) and retries the bump until one succeeds; the marker then clears and caching resumes
under the new epoch. At most one retry is in flight per process: a search that finds one running
sees "pending" at once, issues no SET and waits on nothing.

Guarantee and limit: the marker is process-local. The process that saw a failed bump never serves a
result cached before the write: every failed bump increments a failure generation, and a bump may
clear the marker only if the generation is unchanged since that bump STARTED (see
``invalidate_retrieval_caches``), so a late success cannot undo a newer failure. Another process
(API worker, Celery) cannot be told: with Redis rejecting writes no shared marker can be stored,
and its reads still return the old epoch. Such a process stays stale until its next bump succeeds
or the entry's TTL ends, which is the bounded staleness this design cannot remove.

Logging: entering the degraded state logs one warning, leaving it one info line carrying the
number of failures suppressed in between (those log at debug), so a rejecting Redis cannot flood
the log with one line per search.

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

#: True while a bump failed in this process and no bump started after the latest failure has succeeded.
_pending = False
#: Count of failed bumps in this process; a bump clears ``_pending`` only if it is unchanged since it began.
_failures = 0
#: True while a pending-retry bump is running, so concurrent searches do not each issue their own SET.
_retry_in_flight = False
#: Failures since the degraded state was entered that were not logged above debug; reported on recovery.
_suppressed = 0

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


def _record_failure(reason: str, exc: Exception) -> None:
    """Count a failed bump and mark this process pending; log only the transition into that state."""
    global _pending, _failures, _suppressed
    _failures += 1
    if _pending:
        _suppressed += 1
        logger.debug("Retrieval caches still not invalidated after %s: %s", reason, exc)
        return
    _pending = True
    _suppressed = 0
    logger.warning("Retrieval caches bypassed until an epoch bump succeeds (%s): %s", reason, exc)


def _record_success(reason: str, started_at_failures: int) -> None:
    """Clear the marker only if no bump failed since this one started (see ``invalidate_retrieval_caches``)."""
    global _pending, _suppressed
    if _failures != started_at_failures:
        logger.debug("Epoch bump after %s began before a later failure; caches stay bypassed", reason)
        return
    if _pending:
        logger.info("Epoch bump succeeded after %s; caches resume (%d failures suppressed)", reason, _suppressed)
    _pending = False
    _suppressed = 0
    logger.debug("Retrieval caches invalidated: %s", reason)


async def invalidate_retrieval_caches(reason: str) -> bool:
    """Orphan every cached retrieval result by replacing the KB epoch; ``False`` when that failed.

    Invariant: pending is cleared only by a bump that STARTED after the most recent failure. The
    failure generation is sampled before the first await; a success whose sample no longer matches
    (a bump failed while it was in flight) leaves the marker set, whatever order the replies come in.
    """
    started_at_failures = _failures
    try:
        client = await get_async_redis_client(database=ACL_EPOCH_DATABASE)
        await bump_acl_epoch_async(client)
    except Exception as exc:
        _record_failure(reason, exc)
        return False
    _record_success(reason, started_at_failures)
    return True


async def invalidation_pending() -> bool:
    """True while a bump failed and no later one has cleared it.

    A pending process retries the bump, single-flight: the check-and-set of ``_retry_in_flight`` has
    no await between them, so on the event loop exactly one caller retries and the rest return
    ``True`` without a SET. Its only caller, ``cache_scope``, is async; a plain flag (not a loop-bound
    lock) also holds if searches run on more than one loop.
    """
    global _retry_in_flight
    if not _pending:
        return False
    if _retry_in_flight:
        return True
    _retry_in_flight = True
    try:
        await invalidate_retrieval_caches("pending_retry")
    finally:
        _retry_in_flight = False
    return _pending


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
