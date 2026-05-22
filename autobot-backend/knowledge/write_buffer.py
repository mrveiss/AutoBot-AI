# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LSM-Style Write Buffer for Vector Store Updates (Issue #8158)

Accepts vector writes into an in-memory buffer and asynchronously merges
them to the underlying store. Duplicate IDs within a buffer window are
deduplicated (last-write-wins) before each flush — matching LSM semantics.

Flush is triggered by:
- Buffer reaching FLUSH_SIZE_THRESHOLD entries
- A background task firing every FLUSH_INTERVAL_SECONDS

Usage::

    buffer = VectorWriteBuffer(flush_fn=my_upsert, flush_size=500)
    await buffer.start()
    await buffer.write(id="doc-1", embedding=[...], document="text", metadata={})
    await buffer.stop()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

FLUSH_SIZE_THRESHOLD = 500
FLUSH_INTERVAL_SECONDS = 5.0


@dataclass
class BufferedWrite:
    """A single pending vector write."""

    id: str
    embedding: List[float]
    document: str
    metadata: Dict[str, Any]
    queued_at: float = field(default_factory=time.monotonic)


class VectorWriteBuffer:
    """
    LSM-style in-memory write buffer with async background flush.

    Thread-safety: all mutations are protected by an asyncio.Lock so the
    buffer can be safely shared across concurrent request handlers within a
    single event-loop (uvicorn worker).
    """

    def __init__(
        self,
        flush_fn: Callable[[List[BufferedWrite]], Coroutine[Any, Any, None]],
        flush_size: int = FLUSH_SIZE_THRESHOLD,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
    ) -> None:
        self._flush_fn = flush_fn
        self._flush_size = flush_size
        self._flush_interval = flush_interval
        # ID → entry; new writes overwrite stale ones (last-write-wins)
        self._buffer: Dict[str, BufferedWrite] = {}
        self._lock = asyncio.Lock()
        self._bg_task: Optional[asyncio.Task] = None
        self._flush_count = 0
        self._write_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background flush task."""
        if self._bg_task is None or self._bg_task.done():
            self._bg_task = asyncio.create_task(self._flush_loop(), name="vector-write-buffer-flush")
            logger.info("VectorWriteBuffer started (flush_size=%d, interval=%.1fs)", self._flush_size, self._flush_interval)

    async def stop(self) -> None:
        """Flush remaining entries and stop the background task."""
        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
        await self._flush()
        logger.info("VectorWriteBuffer stopped (total writes=%d, flushes=%d)", self._write_count, self._flush_count)

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    async def write(
        self,
        id: str,
        embedding: List[float],
        document: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Buffer a vector write. If the buffer is full, flush immediately."""
        async with self._lock:
            self._buffer[id] = BufferedWrite(
                id=id,
                embedding=embedding,
                document=document,
                metadata=metadata or {},
            )
            self._write_count += 1
            should_flush = len(self._buffer) >= self._flush_size

        if should_flush:
            await self._flush()

    async def flush_now(self) -> int:
        """Force an immediate flush. Returns number of entries flushed."""
        return await self._flush()

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        """Background task: flush at regular intervals."""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> int:
        """Drain buffer and call flush_fn with the deduplicated batch."""
        async with self._lock:
            if not self._buffer:
                return 0
            batch = list(self._buffer.values())
            self._buffer.clear()
            self._flush_count += 1

        try:
            await self._flush_fn(batch)
            logger.debug("VectorWriteBuffer flushed %d entries (flush #%d)", len(batch), self._flush_count)
        except Exception:
            logger.exception("VectorWriteBuffer flush failed — %d entries dropped", len(batch))

        return len(batch)


def make_chromadb_flush_fn(collection: Any) -> Callable[[List[BufferedWrite]], Coroutine[Any, Any, None]]:
    """
    Build a flush function that upserts buffered writes into a ChromaDB collection.

    The collection argument must expose an async-compatible upsert interface or be
    wrapped with asyncio.to_thread() — this factory handles the wrapping.
    """

    async def _flush(batch: List[BufferedWrite]) -> None:
        ids = [e.id for e in batch]
        embeddings = [e.embedding for e in batch]
        documents = [e.document for e in batch]
        metadatas = [e.metadata for e in batch]
        await asyncio.to_thread(collection.upsert, ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    return _flush
