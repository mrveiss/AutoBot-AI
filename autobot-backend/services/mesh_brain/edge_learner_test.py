# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for EdgeLearner — Hebbian edge reinforcement from retrieval feedback (#2056)."""

import json
from unittest.mock import AsyncMock

import pytest

from services.mesh_brain.edge_learner import EdgeLearner
from tests.fixtures import make_async_redis

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


# Migrated to canonical ``make_async_redis()`` (#7280 round 4).
# Local helper removed — call sites use ``make_async_redis(xrange=[])``
# directly. ``hgetall`` is a canonical default; ``xrange`` flows through
# ``**extra_methods``.


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
    async def test_on_retrieval_reinforces_existing_edge(self) -> None:
        """update_edge is called with EMA-updated weight for an existing edge."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        expected_weight = 0.6 * _EMA_DECAY + 1.0 * (1 - _EMA_DECAY)
        db.update_edge.assert_awaited_once_with("edge-1", weight=pytest.approx(expected_weight), co_access_count=3)

    @pytest.mark.asyncio
    async def test_on_retrieval_creates_edge_above_threshold(self) -> None:
        """create_edge is called once co_access_count reaches creation_threshold."""
        db = _make_db_mock()
        db.get_edge = AsyncMock(return_value=None)
        db.get_co_access_count = AsyncMock(return_value=3)

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ["X", "Y"]})

        db.create_edge.assert_awaited_once_with(
            from_node="X",
            to_node="Y",
            edge_type="CO_RETRIEVED",
            weight=_INITIAL_WEIGHT,
            origin="learner",
        )

    @pytest.mark.asyncio
    async def test_on_retrieval_skips_creation_below_threshold(self) -> None:
        """create_edge is NOT called when co_access_count is below threshold."""
        db = _make_db_mock()
        db.get_edge = AsyncMock(return_value=None)
        db.get_co_access_count = AsyncMock(return_value=2)

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ["X", "Y"]})

        db.create_edge.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_retrieval_updates_access_counts(self) -> None:
        """update_access_count is called with the top-5 IDs."""
        db = _make_db_mock()
        ids = ["A", "B", "C", "D", "E"]

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ids})

        db.update_access_count.assert_awaited_once_with(ids)

    @pytest.mark.asyncio
    async def test_on_retrieval_processes_top_5_only(self) -> None:
        """Only combinations of the first 5 IDs are reinforced, not all 10."""
        db = _make_db_mock()
        ids = [str(i) for i in range(10)]

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ids})

        # top-5 produces C(5,2)=10 pairs; get_edge called exactly 10 times
        assert db.get_edge.await_count == 10
        # update_access_count receives only the first 5
        db.update_access_count.assert_awaited_once_with(ids[:5])

    @pytest.mark.asyncio
    async def test_on_retrieval_handles_json_string_ids(self) -> None:
        """ranked_ids supplied as a JSON string is parsed before processing."""
        db = _make_db_mock()
        ids = ["P", "Q", "R"]

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": json.dumps(ids)})

        db.update_access_count.assert_awaited_once_with(ids)

    @pytest.mark.asyncio
    async def test_on_retrieval_skips_single_result(self) -> None:
        """A single ID produces no combinations, so no reinforcement occurs."""
        db = _make_db_mock()

        learner = _make_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ["only-one"]})

        db.get_edge.assert_not_awaited()
        db.update_edge.assert_not_awaited()
        db.create_edge.assert_not_awaited()
        db.update_access_count.assert_not_awaited()


class TestEdgeLearnerConsumeFeedbackStream:
    """Tests for EdgeLearner.consume_feedback_stream()."""

    @pytest.mark.asyncio
    async def test_consume_feedback_stream_processes_all_entries(self) -> None:
        """All stream entries are passed to on_retrieval and processed count returned."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

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
    async def test_consume_feedback_stream_uses_today_by_default(self) -> None:
        """consume_feedback_stream builds stream key from today's date when date_key is None."""
        from datetime import datetime, timezone

        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        redis.xrange = AsyncMock(return_value=[])

        learner = _make_learner(db, redis)
        await learner.consume_feedback_stream()

        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        expected_key = f"rag:feedback:{today}"
        redis.xrange.assert_awaited_once_with(expected_key, min="0-0", count=100)

    @pytest.mark.asyncio
    async def test_cursor_persists_between_calls_no_duplicate_processing(self) -> None:
        """Second call uses exclusive cursor — no re-processing. Fix: #2102."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

        entry_a = ("1-0", {"final_ranked_ids": json.dumps(["A", "B"])})
        entry_b = ("2-0", {"final_ranked_ids": json.dumps(["C", "D"])})

        # First call: two entries processed, cursor advances to "2-1".
        # Second call: xrange(min="2-1") returns nothing — all consumed.
        redis.xrange = AsyncMock(
            side_effect=[
                [entry_a, entry_b],  # first consume call
                [],  # second call — cursor "2-1" excludes everything
            ]
        )

        learner = _make_learner(db, redis)

        count_first = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_first == 2

        db.update_access_count.reset_mock()

        count_second = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_second == 0
        db.update_access_count.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cursor_advances_when_new_entries_arrive(self) -> None:
        """New entries after cursor are consumed. Fix: #2102."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

        entry_a = ("1-0", {"final_ranked_ids": json.dumps(["A", "B"])})
        entry_b = ("2-0", {"final_ranked_ids": json.dumps(["C", "D"])})
        entry_c = ("3-0", {"final_ranked_ids": json.dumps(["E", "F"])})

        # First call: only entry_a, cursor advances to "1-1".
        # Second call: xrange(min="1-1") returns entry_b + entry_c.
        redis.xrange = AsyncMock(
            side_effect=[
                [entry_a],  # first call
                [entry_b, entry_c],  # second call — new entries only
            ]
        )

        learner = _make_learner(db, redis)

        count_first = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_first == 1

        db.update_access_count.reset_mock()

        count_second = await learner.consume_feedback_stream(date_key="2026-03-23")
        assert count_second == 2
        assert db.update_access_count.await_count == 2


# =============================================================================
# EWC++ catastrophic forgetting prevention tests (#2097)
# =============================================================================


def _make_ewc_learner(db: AsyncMock, redis: AsyncMock, ewc_lambda: float = 0.4) -> EdgeLearner:
    """Return an EdgeLearner with EWC++ enabled at specified lambda."""
    return EdgeLearner(
        db=db,
        redis=redis,
        ema_decay=_EMA_DECAY,
        creation_threshold=_CREATION_THRESHOLD,
        initial_weight=_INITIAL_WEIGHT,
        ewc_lambda=ewc_lambda,
        ewc_consolidation_interval=100,
    )


class TestEWCPrevention:
    """Tests for EWC++ catastrophic forgetting prevention (#2097)."""

    @pytest.mark.asyncio
    async def test_ewc_no_effect_when_lambda_zero(self) -> None:
        """ewc_lambda=0 produces identical weight update to original EMA formula."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_ewc_learner(db, make_async_redis(xrange=[]), ewc_lambda=0.0)
        # Seed a high-importance reference so EWC would normally dampen.
        learner._reference_weights["edge-1"] = 0.6
        learner._importance["edge-1"] = 1.0

        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        expected_weight = 0.6 * _EMA_DECAY + 1.0 * (1 - _EMA_DECAY)
        db.update_edge.assert_awaited_once_with("edge-1", weight=pytest.approx(expected_weight), co_access_count=3)

    @pytest.mark.asyncio
    async def test_ewc_dampens_high_importance_edges(self) -> None:
        """High-importance edge resists drift: final weight is between current and proposed."""
        db = _make_db_mock()
        current_weight = 0.6
        edge = _existing_edge(weight=current_weight, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_ewc_learner(db, make_async_redis(xrange=[]), ewc_lambda=0.4)
        # Seed reference weight equal to current and high importance.
        learner._reference_weights["edge-1"] = current_weight
        learner._importance["edge-1"] = 1.0

        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        proposed = current_weight * _EMA_DECAY + 1.0 * (1 - _EMA_DECAY)
        # Penalty is non-zero; final weight must be strictly between current and proposed.
        call_kwargs = db.update_edge.call_args.kwargs
        final_weight = call_kwargs["weight"]
        assert current_weight < final_weight < proposed

    @pytest.mark.asyncio
    async def test_ewc_allows_update_on_low_importance_edges(self) -> None:
        """Low-importance edges (importance≈0) update almost to the full proposed weight."""
        db = _make_db_mock()
        current_weight = 0.6
        edge = _existing_edge(weight=current_weight, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_ewc_learner(db, make_async_redis(xrange=[]), ewc_lambda=0.4)
        learner._reference_weights["edge-1"] = current_weight
        learner._importance["edge-1"] = 0.0  # no importance → no dampening

        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        proposed = current_weight * _EMA_DECAY + 1.0 * (1 - _EMA_DECAY)
        call_kwargs = db.update_edge.call_args.kwargs
        final_weight = call_kwargs["weight"]
        # With importance=0 the penalty is 0 → dampening=1.0 → full EMA update.
        assert final_weight == pytest.approx(proposed)

    @pytest.mark.asyncio
    async def test_ewc_consolidation_interval(self) -> None:
        """consolidate_weights is called once after ewc_consolidation_interval updates."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=0)
        db.get_edge = AsyncMock(return_value=edge)

        learner = EdgeLearner(
            db=db,
            redis=make_async_redis(xrange=[]),
            ema_decay=_EMA_DECAY,
            creation_threshold=_CREATION_THRESHOLD,
            initial_weight=_INITIAL_WEIGHT,
            ewc_lambda=0.4,
            ewc_consolidation_interval=3,
        )

        consolidation_calls = []

        async def _fake_consolidate() -> None:
            consolidation_calls.append(1)

        learner.consolidate_weights = _fake_consolidate  # type: ignore[method-assign]

        # Drive 3 updates — consolidation should fire exactly once at the 3rd.
        for _ in range(3):
            await learner._update_existing_edge(edge)

        assert len(consolidation_calls) == 1

    @pytest.mark.asyncio
    async def test_update_importance_increases_on_success(self) -> None:
        """update_importance increments importance toward 1.0 on success."""
        db = _make_db_mock()
        learner = _make_ewc_learner(db, make_async_redis(xrange=[]))

        learner.update_importance("edge-1", success=True)
        after_first = learner._importance["edge-1"]
        assert after_first > 0.0

        learner.update_importance("edge-1", success=True)
        after_second = learner._importance["edge-1"]
        assert after_second > after_first

    def test_update_importance_decays_on_failure(self) -> None:
        """update_importance decays toward 0 on non-success."""
        db = _make_db_mock()
        learner = _make_ewc_learner(db, make_async_redis(xrange=[]))

        learner._importance["edge-1"] = 0.5
        learner.update_importance("edge-1", success=False)
        assert learner._importance["edge-1"] == pytest.approx(0.5 * 0.95)

    @pytest.mark.asyncio
    async def test_reference_weights_populated_after_update(self) -> None:
        """_reference_weights is populated with final weight after _update_existing_edge."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_ewc_learner(db, make_async_redis(xrange=[]))
        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        assert "edge-1" in learner._reference_weights
        stored = learner._reference_weights["edge-1"]
        call_kwargs = db.update_edge.call_args.kwargs
        assert stored == pytest.approx(call_kwargs["weight"])

    @pytest.mark.asyncio
    async def test_update_importance_called_on_reinforcement(self) -> None:
        """update_importance(success=True) is called for each reinforced edge (#2546)."""
        db = _make_db_mock()
        edge = _existing_edge(weight=0.6, co_access_count=2)
        db.get_edge = AsyncMock(return_value=edge)

        learner = _make_ewc_learner(db, make_async_redis(xrange=[]))
        assert learner._importance.get("edge-1", 0.0) == 0.0

        await learner.on_retrieval({"final_ranked_ids": ["A", "B"]})

        # Importance must have grown after the successful reinforcement.
        assert learner._importance.get("edge-1", 0.0) > 0.0


# =============================================================================
# EWC++ Redis persistence tests (#2546)
# =============================================================================


class TestEWCRedisPersistence:
    """Tests for EWC++ state load/save via Redis (#2546)."""

    @pytest.mark.asyncio
    async def test_load_ewc_state_restores_reference_weights(self) -> None:
        """_load_ewc_state() populates _reference_weights from Redis hash."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        redis.hgetall = AsyncMock(
            side_effect=[
                {},  # CURSOR_HASH_KEY → no cursors
                {"edge-1": "0.75", "edge-2": "0.5"},  # EWC_REFERENCE_WEIGHTS_KEY
                {},  # EWC_IMPORTANCE_KEY → empty
            ]
        )

        learner = _make_ewc_learner(db, redis)
        await learner.consume_feedback_stream(date_key="2026-03-23")

        assert learner._reference_weights == {
            "edge-1": pytest.approx(0.75),
            "edge-2": pytest.approx(0.5),
        }

    @pytest.mark.asyncio
    async def test_load_ewc_state_restores_importance(self) -> None:
        """_load_ewc_state() populates _importance from Redis hash."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        redis.hgetall = AsyncMock(
            side_effect=[
                {},  # CURSOR_HASH_KEY
                {},  # EWC_REFERENCE_WEIGHTS_KEY
                {"edge-1": "0.3", "edge-3": "0.8"},  # EWC_IMPORTANCE_KEY
            ]
        )

        learner = _make_ewc_learner(db, redis)
        await learner.consume_feedback_stream(date_key="2026-03-23")

        assert learner._importance == {
            "edge-1": pytest.approx(0.3),
            "edge-3": pytest.approx(0.8),
        }

    @pytest.mark.asyncio
    async def test_load_ewc_state_called_only_once(self) -> None:
        """_load_ewc_state() is idempotent — Redis is not queried on subsequent calls."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        # hgetall called 3 times on first consume: cursor + 2 EWC hashes.
        redis.hgetall = AsyncMock(return_value={})

        learner = _make_ewc_learner(db, redis)
        await learner.consume_feedback_stream(date_key="2026-03-23")
        first_call_count = redis.hgetall.await_count  # 3 (cursors + weights + importance)

        await learner.consume_feedback_stream(date_key="2026-03-23")
        # No additional hgetall calls on second consume — state already loaded.
        assert redis.hgetall.await_count == first_call_count

    @pytest.mark.asyncio
    async def test_save_ewc_state_persists_reference_weights(self) -> None:
        """_save_ewc_state() writes reference weights to Redis hash via hset mapping."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

        learner = _make_ewc_learner(db, redis)
        learner._reference_weights = {"edge-1": 0.75}
        learner._importance = {}

        await learner._save_ewc_state()

        redis.hset.assert_any_await(
            EdgeLearner.EWC_REFERENCE_WEIGHTS_KEY,
            mapping={"edge-1": "0.75"},
        )

    @pytest.mark.asyncio
    async def test_save_ewc_state_persists_importance(self) -> None:
        """_save_ewc_state() writes importance scores to Redis hash via hset mapping."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

        learner = _make_ewc_learner(db, redis)
        learner._reference_weights = {}
        learner._importance = {"edge-2": 0.5}

        await learner._save_ewc_state()

        redis.hset.assert_any_await(
            EdgeLearner.EWC_IMPORTANCE_KEY,
            mapping={"edge-2": "0.5"},
        )

    @pytest.mark.asyncio
    async def test_consolidate_weights_calls_save_ewc_state(self) -> None:
        """consolidate_weights() triggers _save_ewc_state() — persisting to Redis (#2546)."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])

        learner = _make_ewc_learner(db, redis)
        learner._reference_weights = {"edge-x": 0.6}
        learner._importance = {"edge-x": 0.4}

        await learner.consolidate_weights()

        # hset must have been called for both EWC hashes.
        hset_keys = [call.args[0] for call in redis.hset.call_args_list]
        assert EdgeLearner.EWC_REFERENCE_WEIGHTS_KEY in hset_keys
        assert EdgeLearner.EWC_IMPORTANCE_KEY in hset_keys

    @pytest.mark.asyncio
    async def test_load_ewc_state_tolerates_redis_failure_on_weights(self) -> None:
        """Redis failure loading reference weights is logged and does not raise (#2546)."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        # First hgetall (cursors) succeeds; second (EWC weights) raises; third (importance) ok.
        redis.hgetall = AsyncMock(side_effect=[{}, RuntimeError("redis down"), {}])

        learner = _make_ewc_learner(db, redis)
        # Must not raise.
        await learner._load_ewc_state()

        assert learner._reference_weights == {}
        assert learner._ewc_state_loaded is True

    @pytest.mark.asyncio
    async def test_load_ewc_state_tolerates_redis_failure_on_importance(self) -> None:
        """Redis failure loading importance is logged and does not raise (#2546)."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        redis.hgetall = AsyncMock(side_effect=[{"edge-1": "0.5"}, RuntimeError("redis down")])

        learner = _make_ewc_learner(db, redis)
        # Bypass cursor load so only 2 hgetall calls needed.
        learner._cursors_loaded = True
        await learner._load_ewc_state()

        assert learner._reference_weights == {"edge-1": pytest.approx(0.5)}
        assert learner._importance == {}
        assert learner._ewc_state_loaded is True

    @pytest.mark.asyncio
    async def test_save_ewc_state_tolerates_redis_failure(self) -> None:
        """Redis failure during save is logged and does not raise (#2546)."""
        db = _make_db_mock()
        redis = make_async_redis(xrange=[])
        redis.hset = AsyncMock(side_effect=RuntimeError("write failed"))

        learner = _make_ewc_learner(db, redis)
        learner._reference_weights = {"edge-1": 0.6}
        learner._importance = {"edge-1": 0.3}

        # Must not raise.
        await learner._save_ewc_state()
