# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Consumer for ``mesh:reembed_queue`` (#20535).

``staleness_propagator.enqueue_for_reembedding`` pushes the doc ids that staleness
propagation flagged. This drains them into the document re-index queue
(``DocIndexerService.enqueue_reindex``), which already dedups by path and retries
the embedding itself, so handing the same id over twice is harmless.

* One consumer: a ``LeaderLease`` elects the worker allowed to drain.
* Crash-safe: each item is LMOVEd to a processing list first; a new leader returns
  leftovers from the previous one to the queue.
* Bounded: an item that fails ``MAX_ATTEMPTS`` times, or names no file, goes to
  ``mesh:reembed_dead`` for inspection instead of looping forever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from autobot_shared.env_registry_mesh_reembed import REEMBED_INTERVAL_DEFAULT_S, reembed_lease_ttl_default_ms
from autobot_shared.env_utils import env_flag, env_int
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Spelled out here (the unconnected-code gate resolves a key from the reading file); a test pins it
# to the producer's key.
QUEUE_KEY = "mesh:reembed_queue"
PROCESSING_KEY = "mesh:reembed_processing"
DEAD_KEY = "mesh:reembed_dead"
ATTEMPTS_KEY = "mesh:reembed_attempts"
LEASE_KEY = "mesh:reembed:leader"

ENABLED = env_flag("AUTOBOT_MESH_REEMBED_ENABLED", True)
INTERVAL_S = env_int("AUTOBOT_MESH_REEMBED_INTERVAL_S", REEMBED_INTERVAL_DEFAULT_S)
BATCH = env_int("AUTOBOT_MESH_REEMBED_BATCH", 100)
# The lease outlives the interval plus a worst-case drain (BATCH items), and drain() also refreshes it
# as it goes, so a second worker never takes it mid-drain and re-queues this worker's in-flight items.
LEASE_TTL_MS = env_int("AUTOBOT_MESH_REEMBED_LEASE_TTL_MS", reembed_lease_ttl_default_ms(INTERVAL_S))
MAX_ATTEMPTS = env_int("AUTOBOT_MESH_REEMBED_MAX_ATTEMPTS", 3)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

Reindex = Callable[[str], Awaitable[Any]]


async def enqueue_reindex(path: str) -> None:
    """Hand *path* to the document indexer's durable sync queue."""
    from services.knowledge.doc_indexer import get_doc_indexer_service
    from services.knowledge.sync_queue import SyncReason

    indexer = get_doc_indexer_service()
    if not await indexer.initialize():
        raise RuntimeError("DocIndexerService not available")
    await indexer.enqueue_reindex(path, reason=SyncReason.CONTENT_CHANGED)


def resolve_doc_path(doc_id: str, root: Path = PROJECT_ROOT) -> str | None:
    """Absolute path of the file *doc_id* names, or None if it names none inside *root*."""
    candidate = (root / doc_id).resolve()
    if candidate.is_relative_to(root.resolve()) and candidate.is_file():
        return str(candidate)
    return None


def _text(raw: Any) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


class ReembedConsumer:
    """Drains ``mesh:reembed_queue``; only the lease holder does so."""

    def __init__(self, redis: Any, reindex: Reindex = enqueue_reindex, root: Path = PROJECT_ROOT) -> None:
        self._redis = redis
        self._reindex = reindex
        self._root = root
        self.lease = LeaderLease(
            key=LEASE_KEY,
            database="main",
            ttl_ms=LEASE_TTL_MS,
            refresh_s=INTERVAL_S,
            poll_s=INTERVAL_S,
            label="Mesh re-embed consumer",
            client_factory=self._lease_client,
        )

    async def _lease_client(self, database: str = "main") -> Any:
        """The lease shares the consumer's Redis client (both are the main DB)."""
        return self._redis

    async def recover_orphans(self) -> int:
        """Return items a previous leader took but never finished to the queue."""
        moved = 0
        while await self._redis.lmove(PROCESSING_KEY, QUEUE_KEY, "LEFT", "RIGHT") is not None:
            moved += 1
        if moved:
            logger.warning("Re-embed consumer: returned %d unfinished items to the queue", moved)
        return moved

    async def dead_letters(self) -> list[str]:
        """Doc ids given up on, for inspection; reported whenever a worker takes the lease."""
        return [_text(item) for item in await self._redis.lrange(DEAD_KEY, 0, -1)]

    async def drain(self) -> int:
        """Handle the items queued now, at most ``BATCH``; returns how many were taken.

        The length is read once, so an id that fails and is re-pushed waits for the next pass instead
        of being retried straight away (a short outage would otherwise dead-letter it). The lease is
        refreshed before each item; if another worker holds it now, the drain stops.
        """
        pending = min(BATCH, int(await self._redis.llen(QUEUE_KEY)))
        taken = 0
        while taken < pending:
            if await self.lease.hold_or_refresh() is False:
                break
            raw = await self._redis.lmove(QUEUE_KEY, PROCESSING_KEY, "LEFT", "RIGHT")
            if raw is None:
                break
            taken += 1
            await self._handle(_text(raw))
        return taken

    async def _handle(self, doc_id: str) -> None:
        path = resolve_doc_path(doc_id, self._root)
        if path is None:
            await self._dead_letter(doc_id, "no such file")
            return
        try:
            await self._reindex(path)
        except Exception as exc:
            await self._failed(doc_id, exc)
            return
        await self._finish(doc_id)

    async def _finish(self, doc_id: str) -> None:
        await self._redis.lrem(PROCESSING_KEY, 1, doc_id)
        await self._redis.hdel(ATTEMPTS_KEY, doc_id)

    async def _failed(self, doc_id: str, exc: Exception) -> None:
        attempts = int(await self._redis.hincrby(ATTEMPTS_KEY, doc_id, 1))
        if attempts >= MAX_ATTEMPTS:
            await self._dead_letter(doc_id, f"{attempts} attempts: {exc}")
            return
        logger.warning("Re-embed of %s failed (attempt %d): %s", doc_id, attempts, exc)
        await self._redis.rpush(QUEUE_KEY, doc_id)
        await self._redis.lrem(PROCESSING_KEY, 1, doc_id)

    async def _dead_letter(self, doc_id: str, reason: str) -> None:
        logger.error("Re-embed dead-lettered %s: %s", doc_id, reason)
        await self._redis.rpush(DEAD_KEY, doc_id)
        await self._finish(doc_id)

    async def _on_acquired(self) -> None:
        await self.recover_orphans()
        dead = await self.dead_letters()
        if dead:
            logger.warning("Re-embed dead-letter list holds %d items (%s)", len(dead), DEAD_KEY)

    async def run(self) -> None:
        """Contest the lease forever; drain while holding it."""
        await self.lease.run(on_tick=self.drain, on_acquired=self._on_acquired)


async def start_reembed_consumer() -> tuple[ReembedConsumer, Any]:
    """Build the consumer on the main Redis DB and retain its task."""
    from autobot_shared.async_compat import fire_and_forget

    redis = await get_async_redis_client(database="main")
    consumer = ReembedConsumer(redis)
    return consumer, fire_and_forget(consumer.run(), name="mesh-reembed-consumer")
