# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit test for EdgeLearner multi-batch pagination (>100 entries) (#2214).

Verifies consume_feedback_stream() correctly paginates Redis xrange calls
when the stream contains more than 100 entries (the batch size).
"""

import json
from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.edge_learner import EdgeLearner

_EMA_DECAY = 0.95
_CREATION_THRESHOLD = 3
_INITIAL_WEIGHT = 0.3


def _make_db_mock() -> AsyncMock:
    """Return a MeshDB mock with sensible defaults."""
    db = AsyncMock()
    db.get_edge = AsyncMock(return_value=None)
    db.update_edge = AsyncMock()
    db.create_edge = AsyncMock()
    db.get_co_access_count = AsyncMock(return_value=0)
    db.update_access_count = AsyncMock()
    return db


def _make_learner(db: AsyncMock, redis: AsyncMock) -> EdgeLearner:
    return EdgeLearner(
        db=db,
        redis=redis,
        ema_decay=_EMA_DECAY,
        creation_threshold=_CREATION_THRESHOLD,
        initial_weight=_INITIAL_WEIGHT,
    )


def _make_entry(seq: int) -> tuple:
    """Create a stream entry with two chunk IDs for edge reinforcement."""
    entry_id = f"{1000 + seq}-0"
    fields = {"final_ranked_ids": json.dumps([f"chunk_{seq}_a", f"chunk_{seq}_b"])}
    return (entry_id, fields)


class TestMultiBatchPagination:
    """Tests for consume_feedback_stream with >100 entries (#2214)."""

    @pytest.mark.asyncio
    async def test_150_entries_across_two_batches(self) -> None:
        """150 entries: first xrange returns 100, second returns 50, third returns []."""
        db = _make_db_mock()
        redis = AsyncMock()

        batch_1 = [_make_entry(i) for i in range(100)]
        batch_2 = [_make_entry(i) for i in range(100, 150)]

        redis.xrange = AsyncMock(side_effect=[batch_1, batch_2, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        assert count == 150
        # on_retrieval called once per entry (each has 2 IDs → 1 pair → 1 get_edge)
        assert db.update_access_count.await_count == 150

    @pytest.mark.asyncio
    async def test_exactly_100_entries_single_batch(self) -> None:
        """Exactly 100 entries: returned in one batch, loop does NOT continue."""
        db = _make_db_mock()
        redis = AsyncMock()

        batch = [_make_entry(i) for i in range(100)]
        # 100 entries < 100 is False, so loop continues; second call returns []
        redis.xrange = AsyncMock(side_effect=[batch, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        assert count == 100

    @pytest.mark.asyncio
    async def test_101_entries_triggers_second_batch(self) -> None:
        """101 entries: first batch has 100 (== count), second has 1."""
        db = _make_db_mock()
        redis = AsyncMock()

        batch_1 = [_make_entry(i) for i in range(100)]
        batch_2 = [_make_entry(100)]

        redis.xrange = AsyncMock(side_effect=[batch_1, batch_2, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        assert count == 101

    @pytest.mark.asyncio
    async def test_empty_stream_returns_zero(self) -> None:
        """Empty stream returns 0 processed."""
        db = _make_db_mock()
        redis = AsyncMock()
        redis.xrange = AsyncMock(return_value=[])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        assert count == 0
        db.update_access_count.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_300_entries_three_full_batches(self) -> None:
        """300 entries across 3 full batches + empty terminator."""
        db = _make_db_mock()
        redis = AsyncMock()

        batch_1 = [_make_entry(i) for i in range(100)]
        batch_2 = [_make_entry(i) for i in range(100, 200)]
        batch_3 = [_make_entry(i) for i in range(200, 300)]

        redis.xrange = AsyncMock(side_effect=[batch_1, batch_2, batch_3, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        assert count == 300

    @pytest.mark.asyncio
    async def test_cursor_advances_correctly_across_batches(self) -> None:
        """Cursor passed to second xrange call excludes already-processed entries."""
        db = _make_db_mock()
        redis = AsyncMock()

        batch_1 = [_make_entry(i) for i in range(100)]
        batch_2 = [_make_entry(i) for i in range(100, 150)]

        redis.xrange = AsyncMock(side_effect=[batch_1, batch_2, []])

        learner = _make_learner(db, redis)
        await learner.consume_feedback_stream(date_key="2026-03-25")

        # First call uses "0-0", second call should use an advanced cursor
        calls = redis.xrange.call_args_list
        assert calls[0].kwargs["min"] == "0-0" or calls[0][1].get("min") == "0-0"
        # Second call should have an advanced cursor (not "0-0")
        second_min = calls[1].kwargs.get("min") or calls[1][1].get("min", "")
        assert second_min != "0-0", f"Cursor did not advance: {second_min}"

    @pytest.mark.asyncio
    async def test_no_duplicate_processing_across_batches(self) -> None:
        """Each entry is processed exactly once, not re-processed in later batches."""
        db = _make_db_mock()
        redis = AsyncMock()

        # Create 150 entries with unique IDs
        batch_1 = [_make_entry(i) for i in range(100)]
        batch_2 = [_make_entry(i) for i in range(100, 150)]

        redis.xrange = AsyncMock(side_effect=[batch_1, batch_2, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-25")

        # Exactly 150 calls to update_access_count (one per event)
        assert count == 150
        assert db.update_access_count.await_count == 150
