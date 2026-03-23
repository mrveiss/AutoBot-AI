# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for EdgeLearner — Hebbian edge reinforcement from retrieval feedback (#2056)."""

import json
from unittest.mock import AsyncMock

import pytest
from services.mesh_brain.edge_learner import EdgeLearner

# =============================================================================
# Helpers
# =============================================================================

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


def _make_redis_mock() -> AsyncMock:
    """Return a Redis mock with xrange returning empty by default."""
    redis = AsyncMock()
    redis.xrange = AsyncMock(return_value=[])
    return redis


def _make_learner(db: AsyncMock, redis: AsyncMock) -> EdgeLearner:
    return EdgeLearner(
        db=db,
        redis=redis,
        ema_decay=_EMA_DECAY,
        creation_threshold=_CREATION_THRESHOLD,
        initial_weight=_INITIAL_WEIGHT,
    )


def _existing_edge(weight: float = 0.6, co_access_count: int = 2) -> dict:
    return {"id": "edge-1", "weight": weight, "co_access_count": co_access_count}


# =============================================================================
# Tests
# =============================================================================


class TestEdgeLearnerOnRetrieval:
    """Tests for EdgeLearner.on_retrieval()."""

    @pytest.mark.asyncio
    async def test_on_retrieval_reinforces_existing_edge(self):
        """update_edge is called with EMA-updated weight for an existing edge."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        expected_weight = 0.6 * _EMA_DECAY + 1.0 * (1 - _EMA_DECAY)
        db.update_edge.assert_awaited_once_with(
            "edge-1", weight=pytest.approx(expected_weight), co_access_count=3
        )

    @pytest.mark.asyncio
    async def test_on_retrieval_creates_edge_above_threshold(self):
        """create_edge is called once co_access_count reaches creation_threshold."""
        db = _make_db_mock()
        db.get_edge = AsyncMock(return_value=None)
        db.get_co_access_count = AsyncMock(return_value=3)

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ["X", "Y"]})

        db.create_edge.assert_awaited_once_with(
            from_node="X",
            to_node="Y",
            edge_type="CO_RETRIEVED",
            weight=_INITIAL_WEIGHT,
            origin="learner",
        )

    @pytest.mark.asyncio
    async def test_on_retrieval_skips_creation_below_threshold(self):
        """create_edge is NOT called when co_access_count is below threshold."""
        db = _make_db_mock()
        db.get_edge = AsyncMock(return_value=None)
        db.get_co_access_count = AsyncMock(return_value=2)

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ["X", "Y"]})

        db.create_edge.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_retrieval_updates_access_counts(self):
        """update_access_count is called with the top-5 IDs."""
        db = _make_db_mock()
        ids = ["A", "B", "C", "D", "E"]

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ids})

        db.update_access_count.assert_awaited_once_with(ids)

    @pytest.mark.asyncio
    async def test_on_retrieval_processes_top_5_only(self):
        """Only combinations of the first 5 IDs are reinforced, not all 10."""
        db = _make_db_mock()
        ids = [str(i) for i in range(10)]

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ids})

        # top-5 produces C(5,2)=10 pairs; get_edge called exactly 10 times
        assert db.get_edge.await_count == 10
        # update_access_count receives only the first 5
        db.update_access_count.assert_awaited_once_with(ids[:5])

    @pytest.mark.asyncio
    async def test_on_retrieval_handles_json_string_ids(self):
        """ranked_ids supplied as a JSON string is parsed before processing."""
        db = _make_db_mock()
        ids = ["P", "Q", "R"]

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": json.dumps(ids)})

        db.update_access_count.assert_awaited_once_with(ids)

    @pytest.mark.asyncio
    async def test_on_retrieval_skips_single_result(self):
        """A single ID produces no combinations, so no reinforcement occurs."""
        db = _make_db_mock()

        learner = _make_learner(db, _make_redis_mock())
        await learner.on_retrieval({"final_ranked_ids": ["only-one"]})

        db.get_edge.assert_not_awaited()
        db.update_edge.assert_not_awaited()
        db.create_edge.assert_not_awaited()
        db.update_access_count.assert_not_awaited()


class TestEdgeLearnerConsumeFeedbackStream:
    """Tests for EdgeLearner.consume_feedback_stream()."""

    @pytest.mark.asyncio
    async def test_consume_feedback_stream_processes_all_entries(self):
        """All stream entries are passed to on_retrieval and processed count returned."""
        db = _make_db_mock()
        redis = _make_redis_mock()

        entries = [
            ("1-0", {"final_ranked_ids": json.dumps(["A", "B", "C"])}),
            ("2-0", {"final_ranked_ids": json.dumps(["D", "E", "F"])}),
        ]
        # First call returns 2 entries (< 100), second call returns empty → loop exits
        redis.xrange = AsyncMock(side_effect=[entries, []])

        learner = _make_learner(db, redis)
        count = await learner.consume_feedback_stream(date_key="2026-03-23")

        assert count == 2
        redis.xrange.assert_any_call("rag:feedback:2026-03-23", min="0-0", count=100)
        # update_access_count called once per event
        assert db.update_access_count.await_count == 2

    @pytest.mark.asyncio
    async def test_consume_feedback_stream_uses_today_by_default(self):
        """consume_feedback_stream builds stream key from today's date when date_key is None."""
        from datetime import datetime, timezone

        db = _make_db_mock()
        redis = _make_redis_mock()
        redis.xrange = AsyncMock(return_value=[])

        learner = _make_learner(db, redis)
        await learner.consume_feedback_stream()

        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        expected_key = f"rag:feedback:{today}"
        redis.xrange.assert_awaited_once_with(expected_key, min="0-0", count=100)

    @pytest.mark.asyncio
    async def test_cursor_persists_between_calls_no_duplicate_processing(self):
        """Second call resumes from cursor — already-seen entry is skipped. Fix: #2102."""
        db = _make_db_mock()
        redis = _make_redis_mock()

        entry_a = ("1-0", {"final_ranked_ids": json.dumps(["A", "B"])})
        entry_b = ("2-0", {"final_ranked_ids": json.dumps(["C", "D"])})

        # First call: two entries; second call: only entry_b visible from cursor "1-0"
        redis.xrange = AsyncMock(
            side_effect=[
                [entry_a, entry_b],  # first consume call
                [
                    entry_b
                ],  # second call resumes from "1-0", Redis returns "2-0" onwards
                [],  # second call inner loop — nothing more
            ]
        )

        learner = _make_learner(db, redis)

        count_first = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_first == 2

        # Reset access_count tracking to measure only the second call's effect
        db.update_access_count.reset_mock()

        count_second = await learner.consume_feedback_stream(date_key="2026-03-23")
        # Second call sees entry_b returned again at cursor boundary; it should be
        # skipped via the cursor-skip guard (entry_id == resume_id and processed==0).
        assert count_second == 0
        db.update_access_count.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cursor_advances_when_new_entries_arrive(self):
        """New entries written after the first call are consumed on the next call. Fix: #2102."""
        db = _make_db_mock()
        redis = _make_redis_mock()

        entry_a = ("1-0", {"final_ranked_ids": json.dumps(["A", "B"])})
        entry_b = ("2-0", {"final_ranked_ids": json.dumps(["C", "D"])})
        entry_c = ("3-0", {"final_ranked_ids": json.dumps(["E", "F"])})

        # First call: only entry_a exists
        # Second call resumes from "1-0"; Redis returns entry_a (the cursor) + entry_b + entry_c
        redis.xrange = AsyncMock(
            side_effect=[
                [entry_a],  # first call
                [
                    entry_a,
                    entry_b,
                    entry_c,
                ],  # second call (entry_a is the cursor boundary)
            ]
        )

        learner = _make_learner(db, redis)

        count_first = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_first == 1

        db.update_access_count.reset_mock()

        count_second = await learner.consume_feedback_stream(date_key="2026-03-23")
        # entry_a is skipped (cursor boundary); entry_b and entry_c are new
        assert count_second == 2
        assert db.update_access_count.await_count == 2
