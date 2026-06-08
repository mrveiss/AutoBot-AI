# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Persistent document sync queue for reliable re-indexing (#4453).

Provides a Redis-backed work queue so document re-indexing survives worker
crashes and gains retry logic, priority ordering, and status tracking.

Design
------
Four Redis keys back the queue (DB: ``main``):

* ``doc_sync:entry:{id}``      hash    – serialized :class:`SyncQueueEntry`
* ``doc_sync:queue:pending``   zset    – entry IDs ordered by priority score
* ``doc_sync:queue:failed``    zset    – entry IDs of terminally-failed work
* ``doc_sync:queue:done``      zset    – entry IDs of completed work (TTL pruned)

Priority scores order pending work so that ``content_changed`` entries are
dequeued before ``model_updated`` which are dequeued before ``manual``.  FIFO
within a priority is preserved by appending a monotonic fractional component
to the score at enqueue time.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENTRY_KEY_PREFIX = "doc_sync:entry:"
_PENDING_KEY = "doc_sync:queue:pending"
_FAILED_KEY = "doc_sync:queue:failed"
_DONE_KEY = "doc_sync:queue:done"
_PENDING_PATH_KEY_PREFIX = "doc_sync:pending_paths:"

MAX_ATTEMPTS = 3
DONE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class SyncReason(str, Enum):
    """Why a document is being re-indexed.

    Priority ordering: lower ``_priority`` is dequeued first.
    """

    CONTENT_CHANGED = "content_changed"
    MODEL_UPDATED = "model_updated"
    MANUAL = "manual"

    @property
    def _priority(self) -> int:
        return {
            SyncReason.CONTENT_CHANGED: 0,
            SyncReason.MODEL_UPDATED: 1,
            SyncReason.MANUAL: 2,
        }[self]


class SyncStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# SyncQueueEntry
# ---------------------------------------------------------------------------


@dataclass
class SyncQueueEntry:
    """A single document re-indexing work item."""

    id: str
    document_path: str
    reason: SyncReason
    status: SyncStatus = SyncStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_redis_mapping(self) -> Dict[str, str]:
        """Serialize to a flat string mapping suitable for Redis HSET."""
        return {
            "id": self.id,
            "document_path": self.document_path,
            "reason": self.reason.value,
            "status": self.status.value,
            "attempts": str(self.attempts),
            "last_error": self.last_error or "",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_redis_mapping(cls, raw: Dict[Any, Any]) -> "SyncQueueEntry":
        """Build an entry from a Redis ``hgetall`` response (bytes-safe)."""

        def _get(key: str, default: str = "") -> str:
            for k in (key, key.encode()):
                if k in raw:
                    v = raw[k]
                    return v.decode() if isinstance(v, bytes) else str(v)
            return default

        return cls(
            id=_get("id"),
            document_path=_get("document_path"),
            reason=SyncReason(_get("reason", SyncReason.MANUAL.value)),
            status=SyncStatus(_get("status", SyncStatus.PENDING.value)),
            attempts=int(_get("attempts", "0") or 0),
            last_error=_get("last_error") or None,
            created_at=_get("created_at"),
            updated_at=_get("updated_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict for JSON API responses."""
        d = asdict(self)
        d["reason"] = self.reason.value
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------------------
# DocumentSyncQueue
# ---------------------------------------------------------------------------


class DocumentSyncQueue:
    """Persistent priority-ordered queue of re-indexing work items.

    A thin wrapper over Redis — a single instance is safe to share across
    callers and across processes because all state lives in Redis.
    """

    def __init__(self, database: str = "main") -> None:
        self._database = database

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _redis(self):
        return await get_async_redis_client(database=self._database)

    @staticmethod
    def _entry_key(entry_id: str) -> str:
        return f"{_ENTRY_KEY_PREFIX}{entry_id}"

    @staticmethod
    def _pending_path_key(path: str) -> str:
        return f"{_PENDING_PATH_KEY_PREFIX}{path}"

    @staticmethod
    def _priority_score(reason: SyncReason) -> float:
        """Compose a priority score: ``priority_bucket + fifo_suffix``.

        Priority bucket uses a 1e12 multiplier so it always dominates the
        FIFO component (``time.time()`` ~ 1.76e9 today, << 1e12). Within a
        bucket the raw timestamp preserves FIFO order.
        """
        return float(reason._priority) * 1e12 + time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue_sync(self, document_path: str, reason: SyncReason) -> SyncQueueEntry:
        """Create a pending entry for ``document_path`` and return it.

        Dedups by ``document_path``: if an entry for this path is already
        pending (or currently being processed), returns that entry instead
        of creating a duplicate.  The secondary key is cleared when the
        entry reaches a terminal state via :meth:`mark_done` or
        :meth:`mark_failed` (permanent failure only).
        """
        redis = await self._redis()
        path_key = self._pending_path_key(document_path)
        existing_id = await redis.get(path_key)
        if existing_id is not None:
            if isinstance(existing_id, bytes):
                existing_id = existing_id.decode()
            raw = await redis.hgetall(self._entry_key(existing_id))
            if raw:
                logger.debug(
                    "enqueue_sync dedup: path=%s already queued as id=%s",
                    document_path,
                    existing_id,
                )
                return SyncQueueEntry.from_redis_mapping(raw)
            # Stale secondary key — entry hash was pruned; fall through.
            await redis.delete(path_key)

        entry = SyncQueueEntry(
            id=str(uuid.uuid4()),
            document_path=document_path,
            reason=reason,
        )
        pipe = redis.pipeline()
        pipe.hset(self._entry_key(entry.id), mapping=entry.to_redis_mapping())
        pipe.zadd(_PENDING_KEY, {entry.id: self._priority_score(reason)})
        pipe.set(path_key, entry.id)
        await pipe.execute()
        logger.info(
            "enqueued sync: path=%s reason=%s id=%s",
            document_path,
            reason.value,
            entry.id,
        )
        return entry

    async def get_next_pending(self) -> SyncQueueEntry | None:
        """Return the highest-priority pending entry without dequeuing it.

        Uses ``zrange`` with ``withscores=False`` to read the smallest-score
        member (priority 0 before 1 before 2, FIFO inside a bucket).

        Note: this is an inspection helper.  Workers must use
        :meth:`claim_next_pending` to avoid the read-then-remove race where
        two workers claim the same entry (#5079).
        """
        redis = await self._redis()
        ids = await redis.zrange(_PENDING_KEY, 0, 0)
        if not ids:
            return None
        entry_id = ids[0]
        if isinstance(entry_id, bytes):
            entry_id = entry_id.decode()
        raw = await redis.hgetall(self._entry_key(entry_id))
        if not raw:
            # Orphaned zset member; clean it up so we don't loop forever.
            await redis.zrem(_PENDING_KEY, entry_id)
            return None
        return SyncQueueEntry.from_redis_mapping(raw)

    async def claim_next_pending(self) -> SyncQueueEntry | None:
        """Atomically claim the highest-priority pending entry.

        Returns the claimed entry (status set to PROCESSING) or ``None`` if
        the queue is empty or another worker won the race for this id.  The
        atomic ``zrem`` acts as the claim token — exactly one caller
        observes ``removed == 1`` for a given id, so double-processing is
        impossible even with multiple worker processes (#5079).
        """
        redis = await self._redis()
        ids = await redis.zrange(_PENDING_KEY, 0, 0)
        if not ids:
            return None
        entry_id = ids[0]
        if isinstance(entry_id, bytes):
            entry_id = entry_id.decode()
        removed = await redis.zrem(_PENDING_KEY, entry_id)
        if not removed:
            return None  # Another worker claimed it first.
        raw = await redis.hgetall(self._entry_key(entry_id))
        if not raw:
            # Orphaned zset member with no hash — nothing to process.
            return None
        entry = SyncQueueEntry.from_redis_mapping(raw)
        now = datetime.now(tz=timezone.utc).isoformat()
        await redis.hset(
            self._entry_key(entry_id),
            mapping={"status": SyncStatus.PROCESSING.value, "updated_at": now},
        )
        entry.status = SyncStatus.PROCESSING
        entry.updated_at = now
        return entry

    async def mark_processing(self, entry_id: str) -> None:
        """Move an entry out of ``pending`` and set status = processing.

        Prefer :meth:`claim_next_pending` in worker loops — this helper is
        retained for tests and admin tooling that want an explicit
        transition.  The secondary ``pending_paths`` key stays set so a
        concurrent enqueue for the same path still dedups to this in-flight
        entry.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        redis = await self._redis()
        pipe = redis.pipeline()
        pipe.hset(
            self._entry_key(entry_id),
            mapping={"status": SyncStatus.PROCESSING.value, "updated_at": now},
        )
        pipe.zrem(_PENDING_KEY, entry_id)
        await pipe.execute()

    async def mark_done(self, entry_id: str) -> None:
        """Mark an entry complete and place it on the TTL-pruned done zset.

        Clears the ``pending_paths`` secondary key so a subsequent re-edit
        of the same path can be re-enqueued (#5080).
        """
        now_dt = datetime.now(tz=timezone.utc)
        now_iso = now_dt.isoformat()
        now_ts = now_dt.timestamp()
        redis = await self._redis()
        # Look up path so we can clear the dedup key alongside the transition.
        raw = await redis.hgetall(self._entry_key(entry_id))
        path = None
        if raw:
            path = SyncQueueEntry.from_redis_mapping(raw).document_path
        pipe = redis.pipeline()
        pipe.hset(
            self._entry_key(entry_id),
            mapping={"status": SyncStatus.DONE.value, "updated_at": now_iso},
        )
        pipe.zrem(_PENDING_KEY, entry_id)
        pipe.zadd(_DONE_KEY, {entry_id: now_ts})
        if path:
            pipe.delete(self._pending_path_key(path))
        await pipe.execute()

    async def mark_failed(self, entry_id: str, error_msg: str) -> SyncQueueEntry:
        """Record a failure; requeue if under :data:`MAX_ATTEMPTS`, else park.

        Returns the updated entry so callers can inspect the new status.
        """
        redis = await self._redis()
        raw = await redis.hgetall(self._entry_key(entry_id))
        if not raw:
            raise KeyError(f"unknown sync entry: {entry_id}")
        entry = SyncQueueEntry.from_redis_mapping(raw)
        entry.attempts += 1
        entry.last_error = error_msg[:1000]  # cap — errors get large fast
        entry.updated_at = datetime.now(tz=timezone.utc).isoformat()

        pipe = redis.pipeline()
        if entry.attempts >= MAX_ATTEMPTS:
            entry.status = SyncStatus.FAILED
            pipe.hset(self._entry_key(entry_id), mapping=entry.to_redis_mapping())
            pipe.zrem(_PENDING_KEY, entry_id)
            pipe.zadd(_FAILED_KEY, {entry_id: time.time()})
            # Terminal failure — free the dedup key so the path can be
            # re-enqueued by a future edit (#5080).
            pipe.delete(self._pending_path_key(entry.document_path))
            logger.error(
                "sync entry %s permanently failed after %d attempts: %s",
                entry_id,
                entry.attempts,
                error_msg,
            )
        else:
            # Re-queue with the same priority class so it retries ahead of
            # lower-priority work.
            entry.status = SyncStatus.PENDING
            pipe.hset(self._entry_key(entry_id), mapping=entry.to_redis_mapping())
            pipe.zadd(_PENDING_KEY, {entry_id: self._priority_score(entry.reason)})
            logger.warning(
                "sync entry %s attempt %d/%d failed: %s (requeued)",
                entry_id,
                entry.attempts,
                MAX_ATTEMPTS,
                error_msg,
            )
        await pipe.execute()
        return entry

    # ------------------------------------------------------------------
    # Admin / introspection
    # ------------------------------------------------------------------

    async def list_entries(self, status: SyncStatus, limit: int = 100, offset: int = 0) -> List[SyncQueueEntry]:
        """List entries with the given status, newest first for non-pending.

        For ``pending`` the queue order (priority ascending) is returned so
        operators can see what is about to run.
        """
        redis = await self._redis()
        key = {
            SyncStatus.PENDING: _PENDING_KEY,
            SyncStatus.FAILED: _FAILED_KEY,
            SyncStatus.DONE: _DONE_KEY,
        }.get(status)
        if key is None:
            return []
        stop = offset + limit - 1
        if status == SyncStatus.PENDING:
            ids = await redis.zrange(key, offset, stop)
        else:
            ids = await redis.zrevrange(key, offset, stop)
        entries: List[SyncQueueEntry] = []
        for entry_id in ids:
            if isinstance(entry_id, bytes):
                entry_id = entry_id.decode()
            raw = await redis.hgetall(self._entry_key(entry_id))
            if raw:
                entries.append(SyncQueueEntry.from_redis_mapping(raw))
        return entries

    async def prune_done(self, older_than_seconds: int = DONE_TTL_SECONDS) -> int:
        """Delete done entries older than the cutoff and return the count."""
        cutoff = time.time() - older_than_seconds
        redis = await self._redis()
        old_ids = await redis.zrangebyscore(_DONE_KEY, min=0, max=cutoff)
        if not old_ids:
            return 0
        decoded = [i.decode() if isinstance(i, bytes) else i for i in old_ids]
        pipe = redis.pipeline()
        for eid in decoded:
            pipe.delete(self._entry_key(eid))
        pipe.zrem(_DONE_KEY, *decoded)
        await pipe.execute()
        return len(decoded)

    async def stats(self) -> Dict[str, int]:
        """Return counts per status for quick admin summaries."""
        redis = await self._redis()
        pipe = redis.pipeline()
        pipe.zcard(_PENDING_KEY)
        pipe.zcard(_FAILED_KEY)
        pipe.zcard(_DONE_KEY)
        pending, failed, done = await pipe.execute()
        return {
            "pending": int(pending or 0),
            "failed": int(failed or 0),
            "done": int(done or 0),
        }

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    async def process_one(
        self,
        processor: Callable[[SyncQueueEntry], Awaitable[None]],
    ) -> SyncQueueEntry | None:
        """Atomically claim one entry and pass it to ``processor``.

        Uses :meth:`claim_next_pending` so concurrent workers cannot both
        process the same entry (#5079).  The processor is an async callable
        that raises on failure.  Returns the processed entry (with its
        final status) or ``None`` if the queue was empty or another worker
        won the race.
        """
        entry = await self.claim_next_pending()
        if entry is None:
            return None
        try:
            await processor(entry)
        except Exception as exc:  # noqa: BLE001 — worker must survive any failure
            return await self.mark_failed(entry.id, str(exc))
        await self.mark_done(entry.id)
        entry.status = SyncStatus.DONE
        return entry


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_queue: DocumentSyncQueue | None = None


def get_document_sync_queue() -> DocumentSyncQueue:
    """Return the process-wide :class:`DocumentSyncQueue` singleton."""
    global _queue
    if _queue is None:
        _queue = DocumentSyncQueue()
    return _queue


# ---------------------------------------------------------------------------
# Worker that processes queue entries by re-indexing via DocIndexerService
# ---------------------------------------------------------------------------


async def _reindex_processor(entry: SyncQueueEntry) -> None:
    """Processor that re-indexes the document referenced by ``entry``.

    Imported lazily to avoid circular imports between ``doc_indexer`` and
    ``sync_queue`` (DocIndexerService enqueues onto this queue).
    """
    from pathlib import Path

    from services.knowledge.doc_indexer import get_doc_indexer_service

    indexer = get_doc_indexer_service()
    if not await indexer.initialize():
        raise RuntimeError("DocIndexerService initialization failed")
    result = await indexer.index_file(Path(entry.document_path), force=True)
    if result.failed:
        # Surface the underlying reason so mark_failed has a useful message.
        raise RuntimeError("; ".join(result.errors) if result.errors else "indexing failed")


class SyncQueueWorker:
    """Background task that drains :class:`DocumentSyncQueue` continuously."""

    def __init__(
        self,
        queue: DocumentSyncQueue | None = None,
        idle_sleep_seconds: float = 2.0,
        processor: Callable[[SyncQueueEntry], Awaitable[None]] | None = None,
    ) -> None:
        self._queue = queue or get_document_sync_queue()
        self._idle_sleep = idle_sleep_seconds
        self._processor = processor or _reindex_processor
        self._running = False
        self._task = None

    async def run(self) -> None:
        """Process entries until stopped.  Intended to be scheduled as a task."""
        import asyncio

        self._running = True
        logger.info("SyncQueueWorker started")
        try:
            while self._running:
                try:
                    processed = await self._queue.process_one(self._processor)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("SyncQueueWorker loop error")
                    processed = None
                if processed is None:
                    await asyncio.sleep(self._idle_sleep)
        finally:
            self._running = False
            logger.info("SyncQueueWorker stopped")

    def stop(self) -> None:
        self._running = False


def serialize_entry_for_api(entry: SyncQueueEntry) -> Dict[str, Any]:
    """Shape an entry for JSON responses (used by the admin endpoint)."""
    return entry.to_dict()


__all__ = [
    "DONE_TTL_SECONDS",
    "DocumentSyncQueue",
    "MAX_ATTEMPTS",
    "SyncQueueEntry",
    "SyncQueueWorker",
    "SyncReason",
    "SyncStatus",
    "get_document_sync_queue",
    "serialize_entry_for_api",
]
