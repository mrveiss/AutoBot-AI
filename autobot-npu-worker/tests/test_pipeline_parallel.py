"""
Tests for cross-host pipeline parallelism (GH#6737 / MVA-1400).

Covers:
  - build_shard_plan: correct layer allocation across workers
  - build_shard_plan: error on insufficient capacity
  - ShardPlan.validate: gap / overlap / under-coverage detection
  - run_pipeline: hidden state flows through workers in order
  - run_pipeline: token_ids returned from last worker
  - discover_workers: failed hosts are excluded, not fatal
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

_npu_root = Path(__file__).parent.parent
for _p in (_npu_root, _npu_root / "workers"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from pipeline_parallel import (  # noqa: E402
    LayerShard,
    ShardPlan,
    WorkerInfo,
    build_shard_plan,
    discover_workers,
    run_pipeline,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_worker(host: str, max_layers: int = 40) -> WorkerInfo:
    return WorkerInfo(host=host, max_layers=max_layers, vram_bytes_per_layer=256 * 1024 * 1024, device="NPU")


# ---------------------------------------------------------------------------
# build_shard_plan
# ---------------------------------------------------------------------------


class TestBuildShardPlan:
    def test_single_worker_covers_all_layers(self):
        workers = [make_worker("http://w1", max_layers=80)]
        plan = build_shard_plan(workers, total_layers=80)
        assert len(plan.shards) == 1
        shard = plan.shards[0]
        assert shard.layer_start == 0
        assert shard.layer_end == 79
        assert shard.is_last is True

    def test_two_workers_split_evenly(self):
        workers = [make_worker("http://w1", 40), make_worker("http://w2", 40)]
        plan = build_shard_plan(workers, total_layers=80)
        assert len(plan.shards) == 2
        assert plan.shards[0].layer_start == 0
        assert plan.shards[0].layer_end == 39
        assert plan.shards[0].is_last is False
        assert plan.shards[1].layer_start == 40
        assert plan.shards[1].layer_end == 79
        assert plan.shards[1].is_last is True

    def test_uneven_split_uses_full_first_worker(self):
        # w1 can hold 32, w2 holds remainder (48)
        workers = [make_worker("http://w1", 32), make_worker("http://w2", 80)]
        plan = build_shard_plan(workers, total_layers=80)
        assert plan.shards[0].layer_end == 31
        assert plan.shards[1].layer_start == 32
        assert plan.shards[1].layer_end == 79

    def test_extra_capacity_leaves_some_workers_idle(self):
        # 3 workers, only 2 needed
        workers = [make_worker("http://w1", 40), make_worker("http://w2", 40), make_worker("http://w3", 40)]
        plan = build_shard_plan(workers, total_layers=60)
        assert len(plan.shards) == 2  # w3 not assigned
        assert plan.shards[-1].is_last is True

    def test_raises_on_insufficient_capacity(self):
        workers = [make_worker("http://w1", 10)]
        with pytest.raises(ValueError, match="Workers can hold"):
            build_shard_plan(workers, total_layers=80)

    def test_raises_on_empty_worker_list(self):
        with pytest.raises(ValueError, match="No workers"):
            build_shard_plan([], total_layers=80)

    def test_raises_on_zero_layers(self):
        with pytest.raises(ValueError, match="total_layers must be positive"):
            build_shard_plan([make_worker("http://w1")], total_layers=0)


# ---------------------------------------------------------------------------
# ShardPlan.validate
# ---------------------------------------------------------------------------


class TestShardPlanValidate:
    def _make_plan(self, shards, total_layers):
        plan = ShardPlan(shards=shards, total_layers=total_layers)
        return plan

    def test_valid_plan_passes(self):
        w = make_worker("http://w1")
        plan = self._make_plan(
            [LayerShard(w, 0, 39, is_last=False), LayerShard(w, 40, 79, is_last=True)],
            total_layers=80,
        )
        plan.validate()  # no exception

    def test_gap_detected(self):
        w = make_worker("http://w1")
        plan = self._make_plan(
            [LayerShard(w, 0, 39, is_last=False), LayerShard(w, 41, 79, is_last=True)],
            total_layers=80,
        )
        with pytest.raises(ValueError, match="Gap or overlap"):
            plan.validate()

    def test_under_coverage_detected(self):
        w = make_worker("http://w1")
        plan = self._make_plan(
            [LayerShard(w, 0, 39, is_last=True)],
            total_layers=80,
        )
        with pytest.raises(ValueError, match="cover 40 layers"):
            plan.validate()

    def test_empty_plan_fails(self):
        plan = ShardPlan(shards=[], total_layers=80)
        with pytest.raises(ValueError, match="empty"):
            plan.validate()


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------


def _make_mock_response(data: Dict[str, Any], status: int = 200):
    """Return an async context-manager mock that yields a response-like object."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    resp.text = AsyncMock(return_value=str(data))

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestRunPipeline:
    def _make_session(self, responses):
        """responses: list of dicts in shard order."""
        session = MagicMock()
        cms = [_make_mock_response(r) for r in responses]
        session.post = MagicMock(side_effect=cms)
        return session

    @pytest.mark.asyncio
    async def test_hidden_state_threaded_through_workers(self):
        w1 = make_worker("http://w1", 40)
        w2 = make_worker("http://w2", 40)
        plan = build_shard_plan([w1, w2], total_layers=80)

        responses = [
            {"hidden_state_out": [0.5] * 512},
            {"token_ids": [42]},
        ]
        session = self._make_session(responses)

        result = await run_pipeline(plan, "llama-70b", [1.0] * 512, session)
        assert result == [42]

        # Second call should have received the first worker's hidden_state_out
        second_call_kwargs = session.post.call_args_list[1]
        payload = second_call_kwargs[1]["json"]
        assert payload["hidden_state"] == [0.5] * 512
        assert payload["layer_start"] == 40
        assert payload["is_last_worker"] is True

    @pytest.mark.asyncio
    async def test_single_worker_returns_token_ids(self):
        w1 = make_worker("http://w1", 80)
        plan = build_shard_plan([w1], total_layers=80)
        session = self._make_session([{"token_ids": [7, 8, 9]}])

        result = await run_pipeline(plan, "model", [0.1] * 256, session)
        assert result == [7, 8, 9]

    @pytest.mark.asyncio
    async def test_http_error_raises_runtime_error(self):
        w1 = make_worker("http://w1", 80)
        plan = build_shard_plan([w1], total_layers=80)

        bad_resp = AsyncMock()
        bad_resp.status = 500
        bad_resp.text = AsyncMock(return_value="internal error")
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=bad_resp)
        cm.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.post = MagicMock(return_value=cm)

        with pytest.raises(RuntimeError, match="returned 500"):
            await run_pipeline(plan, "model", [], session)


# ---------------------------------------------------------------------------
# discover_workers
# ---------------------------------------------------------------------------


class TestDiscoverWorkers:
    @pytest.mark.asyncio
    async def test_reachable_workers_returned(self):
        cap = {"max_layers": 40, "vram_bytes_per_layer": 268435456, "device": "NPU"}

        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=cap)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=cm)

        workers = await discover_workers(["http://w1"], session)
        assert len(workers) == 1
        assert workers[0].max_layers == 40
        assert workers[0].device == "NPU"

    @pytest.mark.asyncio
    async def test_failed_host_excluded_not_fatal(self):
        cap = {"max_layers": 40, "vram_bytes_per_layer": 268435456, "device": "NPU"}

        good_resp = AsyncMock()
        good_resp.status = 200
        good_resp.json = AsyncMock(return_value=cap)
        good_cm = MagicMock()
        good_cm.__aenter__ = AsyncMock(return_value=good_resp)
        good_cm.__aexit__ = AsyncMock(return_value=False)

        bad_cm = MagicMock()
        bad_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("connection refused"))
        bad_cm.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(side_effect=[bad_cm, good_cm])

        workers = await discover_workers(["http://dead", "http://w2"], session)
        assert len(workers) == 1
        assert workers[0].host == "http://w2"

    @pytest.mark.asyncio
    async def test_all_hosts_failed_raises(self):
        bad_cm = MagicMock()
        bad_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("refused"))
        bad_cm.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.get = MagicMock(return_value=bad_cm)

        with pytest.raises(RuntimeError, match="No NPU workers responded"):
            await discover_workers(["http://dead"], session)
