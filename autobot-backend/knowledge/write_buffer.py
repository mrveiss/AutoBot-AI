# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
        on_flush_error: Optional[Callable[[int, Exception], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        self._flush_fn = flush_fn
        self._flush_size = flush_size
        self._flush_interval = flush_interval
        # Issue #8406: Optional callback invoked with (dropped_count, exc) on flush failure.
        self._on_flush_error = on_flush_error
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
            logger.info(
                "VectorWriteBuffer started (flush_size=%d, interval=%.1fs)", self._flush_size, self._flush_interval
            )

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
        """Buffer a vector write. If the buffer is full, flush immediately.

        Issue #10941: Reject entries with empty/None embeddings — they cause
        IndexError in chroma normalize_insert_record_set and contaminate the
        entire flush batch, silently dropping all valid vectors alongside them.
        """
        if not embedding:
            logger.warning(
                "VectorWriteBuffer.write: dropping id=%r — embedding is empty/None "
                "(embedding generation failed upstream); vector will NOT be stored",
                id,
            )
            return
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
        except Exception as exc:
            logger.exception("VectorWriteBuffer flush failed — %d entries dropped", len(batch))
            if self._on_flush_error is not None:
                try:
                    await self._on_flush_error(len(batch), exc)
                except Exception:
                    logger.exception("on_flush_error callback raised")

        return len(batch)


def make_chromadb_flush_fn(vector_store: Any) -> Callable[[List[BufferedWrite]], Coroutine[Any, Any, None]]:
    """
    Build a flush function that adds buffered writes via a LlamaIndex ChromaVectorStore.

    Uses vector_store.add(nodes) to preserve LlamaIndex internal metadata fields
    (_node_content, _node_type, ref_doc_id) needed for NodeWithScore reconstruction.
    Direct collection.upsert() bypasses these fields — Issue #8401.

    Issue #10941: Filters out entries with empty/None embeddings before calling
    vector_store.add so a single failed embedding cannot raise IndexError inside
    chroma normalize_insert_record_set and drop the entire flush batch.
    """

    async def _flush(batch: List[BufferedWrite]) -> None:
        from llama_index.core.schema import TextNode

        valid: List[BufferedWrite] = []
        for e in batch:
            if e.embedding:
                valid.append(e)
            else:
                logger.warning(
                    "make_chromadb_flush_fn: skipping id=%r — embedding is empty/None; "
                    "vector will NOT be stored in ChromaDB",
                    e.id,
                )

        if not valid:
            logger.warning(
                "make_chromadb_flush_fn: all %d entries had empty embeddings — skipping vector_store.add",
                len(batch),
            )
            return

        nodes = [
            TextNode(
                id_=e.id,
                text=e.document,
                embedding=e.embedding,
                metadata=e.metadata,
            )
            for e in valid
        ]
        await asyncio.to_thread(vector_store.add, nodes)

    return _flush
