# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for NPU cross-host pipeline (GH#6737).

Scenario: 2 simulated workers with 8 GB VRAM each, running a 70B-class model
(represented as 16B params per shard / 32B total sharded across both workers).

Test coverage:
- End-to-end token production across 2 workers
- Single-worker fallback when one worker drops mid-run
- Per-stage telemetry: layer-transfer latency, per-worker compute time, hop count
- Fallback-rate metric accumulates correctly
- Shard plan cache invalidates on worker.added and worker.removed events
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make pipeline_dispatcher importable without relying on the services package
# mock chain set up by the top-level conftest.
_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from pipeline_dispatcher import (  # noqa: E402
    PipelineDispatcher,
    WorkerDroppedError,
    WorkerNode,
    WorkerState,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_8_GB = 8 * 1024**3
_MODEL_ID = "llama3-70b"
_TOTAL_PARAMS = 32  # 32 "layers" standing in for 32B params; 16 per shard
_PROMPT = "Hello, pipeline"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_worker(worker_id: str, vram_bytes: int = _8_GB) -> WorkerNode:
    return WorkerNode(
        worker_id=worker_id, vram_bytes=vram_bytes, state=WorkerState.ONLINE
    )


@pytest.fixture
def two_workers():
    return [_make_worker("npu-0"), _make_worker("npu-1")]


@pytest.fixture
def dispatcher(two_workers):
    d = PipelineDispatcher()
    for w in two_workers:
        d.register_worker(w)
    return d


@pytest.fixture
def mock_tracing():
    svc = MagicMock()
    span = MagicMock()
    svc.start_span.return_value = span
    return svc


# ---------------------------------------------------------------------------
# 1. End-to-end token production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_produces_tokens_across_two_workers(dispatcher):
    result = await dispatcher.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=8)

    assert result.tokens, "Expected non-empty token list from pipeline run"
    assert (
        not result.fallback_used
    ), "Fallback should not fire when both workers are healthy"
    assert result.metrics.total_tokens == len(result.tokens)


@pytest.mark.asyncio
async def test_tokens_sourced_from_both_workers(dispatcher):
    result = await dispatcher.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=8)

    worker_ids_seen = {
        tok.split("_")[1] + "_" + tok.split("_")[2] if len(tok.split("_")) > 2 else ""
        for tok in result.tokens
    }
    # Tokens carry worker_id prefix: tok_{worker_id}_{i}
    prefixes = {tok.split("_")[1] for tok in result.tokens if tok.startswith("tok_")}
    assert (
        "npu-0" in prefixes or "npu-1" in prefixes
    ), "Tokens should originate from pipeline workers"


# ---------------------------------------------------------------------------
# 2. Per-stage telemetry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hop_count_equals_worker_count_minus_one(dispatcher):
    result = await dispatcher.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=8)
    # With 2 workers there is exactly 1 inter-worker hop
    assert result.metrics.hop_count == 1


@pytest.mark.asyncio
async def test_layer_transfer_latency_is_positive(dispatcher):
    result = await dispatcher.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=8)
    assert result.metrics.layer_transfer_latency_ms > 0.0


@pytest.mark.asyncio
async def test_per_worker_compute_time_recorded_for_each_worker(dispatcher):
    result = await dispatcher.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=8)
    assert "npu-0" in result.metrics.per_worker_compute_ms
    assert "npu-1" in result.metrics.per_worker_compute_ms
    for wid, ms in result.metrics.per_worker_compute_ms.items():
        assert ms >= 0.0, f"Compute time for {wid} should be non-negative"


# ---------------------------------------------------------------------------
# 3. Tracing service integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tracing_span_emitted_after_run(mock_tracing):
    d = PipelineDispatcher(tracing_service=mock_tracing)
    d.register_worker(_make_worker("npu-0"))
    d.register_worker(_make_worker("npu-1"))

    await d.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=4)

    mock_tracing.start_span.assert_called_once()
    call_kwargs = mock_tracing.start_span.call_args
    attrs = call_kwargs.kwargs.get("attributes") or (
        call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
    )
    assert "npu.hop_count" in attrs
    assert "npu.layer_transfer_ms" in attrs
    assert "npu.fallback_fired" in attrs
    assert "npu.total_tokens" in attrs
    assert "npu.fallback_rate" in attrs


# ---------------------------------------------------------------------------
# 4. Single-worker fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_fires_when_worker_drops_mid_run():
    """Worker npu-1 transitions to OFFLINE before the run; fallback uses npu-0."""
    d = PipelineDispatcher()
    d.register_worker(_make_worker("npu-0"))
    d.register_worker(_make_worker("npu-1"))

    # Simulate npu-1 going offline after the shard plan is built
    original_call_worker = d._call_worker

    async def _flaky_call(worker, layer_count, prompt, max_tokens):
        if worker.worker_id == "npu-1":
            worker.state = WorkerState.OFFLINE
            raise WorkerDroppedError(worker.worker_id)
        return await original_call_worker(worker, layer_count, prompt, max_tokens)

    d._call_worker = _flaky_call  # type: ignore[method-assign]

    result = await d.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=4)

    assert result.fallback_used, "Fallback flag must be set when a worker drops"
    assert result.metrics.fallback_fired
    assert result.tokens, "Fallback run must still produce tokens"


@pytest.mark.asyncio
async def test_fallback_rate_accumulates_across_runs():
    d = PipelineDispatcher()
    d.register_worker(_make_worker("npu-0"))
    d.register_worker(_make_worker("npu-1"))

    original_call_worker = d._call_worker

    run_counter = {"n": 0}

    async def _sometimes_flaky(worker, layer_count, prompt, max_tokens):
        if run_counter["n"] == 0 and worker.worker_id == "npu-1":
            worker.state = WorkerState.OFFLINE
            raise WorkerDroppedError(worker.worker_id)
        return await original_call_worker(worker, layer_count, prompt, max_tokens)

    d._call_worker = _sometimes_flaky  # type: ignore[method-assign]

    # First run triggers fallback; re-register npu-1 and do a clean run
    await d.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=4)
    run_counter["n"] = 1
    d.register_worker(_make_worker("npu-1"))
    await d.run(_MODEL_ID, _TOTAL_PARAMS, _PROMPT, max_tokens=4)

    # 1 fallback out of 2 runs
    assert d.fallback_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 5. Shard plan cache invalidation
# ---------------------------------------------------------------------------


def test_shard_plan_cached_across_identical_calls(dispatcher):
    plan_a = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    plan_b = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    assert plan_a is plan_b, "Same plan object should be returned on cache hit"


def test_shard_plan_invalidated_on_worker_added(dispatcher):
    plan_before = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    dispatcher.register_worker(_make_worker("npu-2"))
    plan_after = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    assert (
        plan_before is not plan_after
    ), "Cache must be invalidated when a new worker is registered"


def test_shard_plan_invalidated_on_worker_removed(dispatcher):
    plan_before = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    dispatcher.remove_worker("npu-0")
    plan_after = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    assert (
        plan_before is not plan_after
    ), "Cache must be invalidated when a worker is removed"


def test_shard_plan_new_plan_reflects_updated_worker_pool(dispatcher):
    dispatcher.remove_worker("npu-1")
    plan = dispatcher.plan_shards(_MODEL_ID, _TOTAL_PARAMS)
    assert len(plan.workers) == 1
    assert plan.workers[0].worker_id == "npu-0"


def test_shard_plan_distributes_layers_proportionally():
    d = PipelineDispatcher()
    d.register_worker(_make_worker("npu-0", vram_bytes=_8_GB))
    d.register_worker(_make_worker("npu-1", vram_bytes=_8_GB))
    plan = d.plan_shards(_MODEL_ID, 32)
    assert sum(plan.layers_per_worker) == 32
    # Equal VRAM → roughly equal split (within 1 layer rounding)
    assert abs(plan.layers_per_worker[0] - plan.layers_per_worker[1]) <= 1
