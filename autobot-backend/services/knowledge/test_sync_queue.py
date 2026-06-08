# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the document sync queue (#4453).

Uses an in-memory fake Redis so we can exercise the full state machine
(enqueue → process → mark done/failed, priority ordering, retry cap)
without a running Redis server or optional fakeredis dependency.
"""

from __future__ import annotations

import asyncio
import time
from typing import List
from unittest.mock import patch

import pytest

from services.knowledge.sync_queue import (
    MAX_ATTEMPTS,
    DocumentSyncQueue,
    SyncQueueEntry,
    SyncQueueWorker,
    SyncReason,
    SyncStatus,
)
from tests.helpers.fake_redis import AsyncFullFakeRedis


@pytest.fixture
def fake_redis() -> AsyncFullFakeRedis:
    return AsyncFullFakeRedis()


@pytest.fixture
def queue(fake_redis: AsyncFullFakeRedis) -> DocumentSyncQueue:
    """A :class:`DocumentSyncQueue` patched to return the in-memory fake."""

    async def _return_redis(database: str = "main"):
        return fake_redis

    q = DocumentSyncQueue()
    patcher = patch.object(q, "_redis", _return_redis)
    patcher.start()
    yield q
    patcher.stop()


# ---------------------------------------------------------------------------
# Enqueue / dequeue
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    @pytest.mark.asyncio
    async def test_enqueue_returns_pending_entry(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)

        assert entry.document_path == "docs/a.md"
        assert entry.reason == SyncReason.CONTENT_CHANGED
        assert entry.status == SyncStatus.PENDING
        assert entry.attempts == 0

    @pytest.mark.asyncio
    async def test_get_next_pending_returns_enqueued_entry(self, queue: DocumentSyncQueue) -> None:
        enq = await queue.enqueue_sync("docs/a.md", SyncReason.MANUAL)

        nxt = await queue.get_next_pending()

        assert nxt is not None
        assert nxt.id == enq.id
        assert nxt.document_path == "docs/a.md"

    @pytest.mark.asyncio
    async def test_empty_queue_returns_none(self, queue: DocumentSyncQueue) -> None:
        assert await queue.get_next_pending() is None


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    @pytest.mark.asyncio
    async def test_content_changed_dequeued_before_manual(self, queue: DocumentSyncQueue) -> None:
        # Enqueue manual FIRST so FIFO would return it without priority.
        await queue.enqueue_sync("manual.md", SyncReason.MANUAL)
        # Small await gap so monotonic-suffix does not order them backwards.
        await asyncio.sleep(0)
        changed = await queue.enqueue_sync("changed.md", SyncReason.CONTENT_CHANGED)

        nxt = await queue.get_next_pending()

        assert nxt is not None
        assert nxt.id == changed.id
        assert nxt.reason == SyncReason.CONTENT_CHANGED

    @pytest.mark.asyncio
    async def test_priority_beats_fifo_across_one_second_gap(
        self, queue: DocumentSyncQueue, fake_redis: AsyncFullFakeRedis
    ) -> None:
        """Regression for #5078: FIFO component must not overflow priority bucket.

        With the old ``float(priority) + time.time() * 1e-9`` formula the
        FIFO component was ~1.76 today — larger than the priority gap of 1
        — so a MANUAL entry enqueued first would incorrectly come out ahead
        of a later CONTENT_CHANGED entry.  Simulate the 1-second enqueue
        gap by back-dating MANUAL's score in the fake zset and verify
        CONTENT_CHANGED still wins.
        """
        manual = await queue.enqueue_sync("manual.md", SyncReason.MANUAL)
        changed = await queue.enqueue_sync("changed.md", SyncReason.CONTENT_CHANGED)

        # MANUAL was enqueued 1 second earlier than CONTENT_CHANGED.
        now = time.time()
        fake_redis.zsets["doc_sync:queue:pending"][manual.id] = 2.0 * 1e12 + (now - 1.0)
        fake_redis.zsets["doc_sync:queue:pending"][changed.id] = 0.0 * 1e12 + now

        nxt = await queue.get_next_pending()

        assert nxt is not None
        assert nxt.id == changed.id
        assert nxt.reason == SyncReason.CONTENT_CHANGED

    @pytest.mark.asyncio
    async def test_model_updated_between_content_and_manual(self, queue: DocumentSyncQueue) -> None:
        manual = await queue.enqueue_sync("m.md", SyncReason.MANUAL)
        await asyncio.sleep(0)
        model = await queue.enqueue_sync("mdl.md", SyncReason.MODEL_UPDATED)
        await asyncio.sleep(0)
        content = await queue.enqueue_sync("c.md", SyncReason.CONTENT_CHANGED)

        # Drain in priority order.
        first = await queue.get_next_pending()
        assert first.id == content.id
        await queue.mark_done(first.id)

        second = await queue.get_next_pending()
        assert second.id == model.id
        await queue.mark_done(second.id)

        third = await queue.get_next_pending()
        assert third.id == manual.id


# ---------------------------------------------------------------------------
# Atomic claim (#5079)
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    @pytest.mark.asyncio
    async def test_claim_next_pending_returns_and_removes(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)

        claimed = await queue.claim_next_pending()

        assert claimed is not None
        assert claimed.id == entry.id
        assert claimed.status == SyncStatus.PROCESSING
        # Queue is now empty — no second claim possible.
        assert await queue.claim_next_pending() is None

    @pytest.mark.asyncio
    async def test_claim_next_pending_empty_queue_returns_none(self, queue: DocumentSyncQueue) -> None:
        assert await queue.claim_next_pending() is None

    @pytest.mark.asyncio
    async def test_concurrent_claims_only_one_wins(self, queue: DocumentSyncQueue) -> None:
        """Two workers calling claim_next_pending concurrently — exactly one gets it."""
        await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)

        results = await asyncio.gather(
            queue.claim_next_pending(),
            queue.claim_next_pending(),
        )

        # Exactly one result is non-None; the other is None.
        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        assert winners[0].status == SyncStatus.PROCESSING


# ---------------------------------------------------------------------------
# Path deduplication (#5080)
# ---------------------------------------------------------------------------


class TestPathDedup:
    @pytest.mark.asyncio
    async def test_duplicate_enqueue_returns_existing_entry(self, queue: DocumentSyncQueue) -> None:
        first = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)
        second = await queue.enqueue_sync("docs/a.md", SyncReason.MANUAL)

        # Same entry returned — not a new one.
        assert second.id == first.id
        # Only one pending entry in the queue.
        stats = await queue.stats()
        assert stats["pending"] == 1

    @pytest.mark.asyncio
    async def test_reenqueue_allowed_after_mark_done(self, queue: DocumentSyncQueue) -> None:
        first = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)
        await queue.mark_processing(first.id)
        await queue.mark_done(first.id)

        # Path is free again — a fresh enqueue creates a new entry.
        second = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)

        assert second.id != first.id
        stats = await queue.stats()
        assert stats["pending"] == 1
        assert stats["done"] == 1

    @pytest.mark.asyncio
    async def test_reenqueue_allowed_after_terminal_failure(self, queue: DocumentSyncQueue) -> None:
        first = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)
        for _ in range(MAX_ATTEMPTS):
            await queue.mark_processing(first.id)
            await queue.mark_failed(first.id, "boom")

        # Terminal failure frees the dedup key.
        second = await queue.enqueue_sync("docs/a.md", SyncReason.CONTENT_CHANGED)
        assert second.id != first.id


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    @pytest.mark.asyncio
    async def test_mark_processing_removes_from_pending(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)

        await queue.mark_processing(entry.id)

        assert await queue.get_next_pending() is None
        pending = await queue.list_entries(SyncStatus.PENDING)
        assert pending == []

    @pytest.mark.asyncio
    async def test_mark_done_moves_to_done_collection(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)
        await queue.mark_processing(entry.id)

        await queue.mark_done(entry.id)

        stats = await queue.stats()
        assert stats["done"] == 1
        assert stats["pending"] == 0
        assert stats["failed"] == 0


# ---------------------------------------------------------------------------
# Retry / failure semantics
# ---------------------------------------------------------------------------


class TestFailureAndRetry:
    @pytest.mark.asyncio
    async def test_failed_under_limit_requeues(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)
        await queue.mark_processing(entry.id)

        updated = await queue.mark_failed(entry.id, "transient embedding error")

        assert updated.status == SyncStatus.PENDING
        assert updated.attempts == 1
        assert updated.last_error == "transient embedding error"
        # The entry should be back on the pending queue for retry.
        nxt = await queue.get_next_pending()
        assert nxt is not None and nxt.id == entry.id

    @pytest.mark.asyncio
    async def test_mark_failed_three_times_terminates_as_failed(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)

        for attempt in range(MAX_ATTEMPTS):
            await queue.mark_processing(entry.id)
            updated = await queue.mark_failed(entry.id, f"attempt {attempt} failed")

        assert updated.status == SyncStatus.FAILED
        assert updated.attempts == MAX_ATTEMPTS
        assert updated.last_error == f"attempt {MAX_ATTEMPTS - 1} failed"
        stats = await queue.stats()
        assert stats["failed"] == 1
        assert stats["pending"] == 0

    @pytest.mark.asyncio
    async def test_failed_entries_appear_in_list_entries(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)
        for _ in range(MAX_ATTEMPTS):
            await queue.mark_processing(entry.id)
            await queue.mark_failed(entry.id, "boom")

        failed = await queue.list_entries(SyncStatus.FAILED)

        assert len(failed) == 1
        assert failed[0].id == entry.id
        assert failed[0].status == SyncStatus.FAILED


# ---------------------------------------------------------------------------
# Worker loop via process_one()
# ---------------------------------------------------------------------------


class TestWorkerLoop:
    @pytest.mark.asyncio
    async def test_process_one_runs_processor_and_marks_done(self, queue: DocumentSyncQueue) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)
        called: List[str] = []

        async def processor(e: SyncQueueEntry) -> None:
            called.append(e.id)

        processed = await queue.process_one(processor)

        assert processed is not None
        assert processed.id == entry.id
        assert called == [entry.id]
        stats = await queue.stats()
        assert stats["done"] == 1
        assert stats["pending"] == 0

    @pytest.mark.asyncio
    async def test_process_one_records_failure_and_requeues(self, queue: DocumentSyncQueue) -> None:
        await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)

        async def processor(_: SyncQueueEntry) -> None:
            raise RuntimeError("embedding model offline")

        result = await queue.process_one(processor)

        assert result is not None
        assert result.status == SyncStatus.PENDING  # retry
        assert result.attempts == 1
        assert "embedding model offline" in (result.last_error or "")
        stats = await queue.stats()
        assert stats["pending"] == 1

    @pytest.mark.asyncio
    async def test_process_one_empty_queue_returns_none(self, queue: DocumentSyncQueue) -> None:
        async def processor(_: SyncQueueEntry) -> None:
            pytest.fail("processor must not run on empty queue")

        assert await queue.process_one(processor) is None

    @pytest.mark.asyncio
    async def test_sync_queue_worker_drains_pending(self, queue: DocumentSyncQueue) -> None:
        """SyncQueueWorker.run() processes pending entries and idles otherwise."""
        processed_ids: List[str] = []

        async def processor(e: SyncQueueEntry) -> None:
            processed_ids.append(e.id)

        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)
        worker = SyncQueueWorker(queue=queue, idle_sleep_seconds=0.01, processor=processor)
        task = asyncio.create_task(worker.run())

        # Let the worker pick up the entry.
        for _ in range(50):
            await asyncio.sleep(0.01)
            if processed_ids:
                break

        worker.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert processed_ids == [entry.id]


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------


class TestPrune:
    @pytest.mark.asyncio
    async def test_prune_done_removes_expired_entries(
        self, queue: DocumentSyncQueue, fake_redis: AsyncFullFakeRedis
    ) -> None:
        entry = await queue.enqueue_sync("a.md", SyncReason.MANUAL)
        await queue.mark_processing(entry.id)
        await queue.mark_done(entry.id)

        # Back-date the done-zset score so the entry is "old".
        fake_redis.zsets["doc_sync:queue:done"][entry.id] = 0.0

        pruned = await queue.prune_done(older_than_seconds=3600)

        assert pruned == 1
        stats = await queue.stats()
        assert stats["done"] == 0


# ---------------------------------------------------------------------------
# Admin endpoint integration (smoke test without FastAPI)
# ---------------------------------------------------------------------------


class TestAdminEndpoint:
    @pytest.mark.asyncio
    async def test_admin_endpoint_returns_pending_and_failed(self, queue: DocumentSyncQueue) -> None:
        from api.knowledge_sync_queue import get_sync_queue

        pending_entry = await queue.enqueue_sync("a.md", SyncReason.CONTENT_CHANGED)
        failed_entry = await queue.enqueue_sync("b.md", SyncReason.MANUAL)
        for _ in range(MAX_ATTEMPTS):
            await queue.mark_processing(failed_entry.id)
            await queue.mark_failed(failed_entry.id, "nope")

        with patch("api.knowledge_sync_queue.get_document_sync_queue", return_value=queue):
            response = await get_sync_queue(limit=10, offset=0, admin_check=True)

        pending_ids = {e["id"] for e in response["pending"]}
        failed_ids = {e["id"] for e in response["failed"]}
        assert pending_entry.id in pending_ids
        assert failed_entry.id in failed_ids
        assert response["counts"]["pending"] == 1
        assert response["counts"]["failed"] == 1
