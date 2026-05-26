# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for shard_planner (MVA-1096)."""

import pytest

from shard_planner import (
    InsufficientPoolError,
    LayerRange,
    ModelDescriptor,
    ShardAssignment,
    WorkerPoolEntry,
    plan_id_for,
    plan_shards,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model(layers: int = 32, model_id: str = "test-model") -> ModelDescriptor:
    return ModelDescriptor(model_id=model_id, total_layers=layers)


def _worker(worker_id: str, vram_gb: float, enabled: bool = True) -> WorkerPoolEntry:
    return WorkerPoolEntry(
        worker_id=worker_id,
        vram_bytes=int(vram_gb * 1024**3),
        enabled=enabled,
    )


def _total_layers(assignments: list[ShardAssignment]) -> int:
    return sum(a.layer_range.count for a in assignments)


def _no_overlap(assignments: list[ShardAssignment]) -> bool:
    seen: set[int] = set()
    for a in assignments:
        for layer in range(a.layer_range.start, a.layer_range.end + 1):
            if layer in seen:
                return False
            seen.add(layer)
    return True


# ---------------------------------------------------------------------------
# Single-worker fallback
# ---------------------------------------------------------------------------


class TestSingleWorker:
    def test_single_worker_gets_all_layers(self):
        pool = [_worker("w1", 16)]
        result = plan_shards(_model(32), pool)
        assert len(result) == 1
        assert result[0].worker_id == "w1"
        assert result[0].layer_range == LayerRange(0, 31)

    def test_single_worker_small_model(self):
        pool = [_worker("w1", 4)]
        result = plan_shards(_model(4), pool)
        assert _total_layers(result) == 4


# ---------------------------------------------------------------------------
# Heterogeneous VRAM
# ---------------------------------------------------------------------------


class TestHeterogeneousVRAM:
    def test_two_workers_proportional(self):
        pool = [_worker("big", 16), _worker("small", 8)]
        result = plan_shards(_model(30), pool)
        assert _total_layers(result) == 30
        assert _no_overlap(result)
        big = next(a for a in result if a.worker_id == "big")
        small = next(a for a in result if a.worker_id == "small")
        assert big.layer_range.count >= small.layer_range.count

    def test_full_layer_coverage(self):
        pool = [_worker("a", 8), _worker("b", 4), _worker("c", 12)]
        result = plan_shards(_model(48), pool)
        assert _total_layers(result) == 48
        assert _no_overlap(result)
        starts = sorted(a.layer_range.start for a in result)
        assert starts[0] == 0

    def test_three_equal_workers(self):
        pool = [_worker(f"w{i}", 8) for i in range(3)]
        result = plan_shards(_model(30), pool)
        assert _total_layers(result) == 30
        assert _no_overlap(result)
        for a in result:
            assert 9 <= a.layer_range.count <= 11

    def test_disabled_workers_excluded(self):
        pool = [_worker("enabled", 8), _worker("disabled", 100, enabled=False)]
        result = plan_shards(_model(16), pool)
        assert all(a.worker_id == "enabled" for a in result)

    def test_remainder_layers_assigned(self):
        """All layers covered when total_layers is not divisible evenly."""
        pool = [_worker("w1", 1), _worker("w2", 1), _worker("w3", 1)]
        result = plan_shards(_model(10), pool)
        assert _total_layers(result) == 10
        assert _no_overlap(result)


# ---------------------------------------------------------------------------
# Insufficient pool
# ---------------------------------------------------------------------------


class TestInsufficientPool:
    def test_empty_pool_raises(self):
        with pytest.raises(InsufficientPoolError):
            plan_shards(_model(32), [])

    def test_all_disabled_raises(self):
        pool = [_worker("w1", 16, enabled=False), _worker("w2", 8, enabled=False)]
        with pytest.raises(InsufficientPoolError):
            plan_shards(_model(32), pool)

    def test_zero_vram_workers_raises(self):
        pool = [WorkerPoolEntry(worker_id="w1", vram_bytes=0)]
        with pytest.raises(InsufficientPoolError):
            plan_shards(_model(32), pool)

    def test_invalid_layer_count_raises(self):
        pool = [_worker("w1", 8)]
        with pytest.raises(ValueError):
            plan_shards(_model(0), pool)


# ---------------------------------------------------------------------------
# plan_id_for
# ---------------------------------------------------------------------------


class TestPlanId:
    def test_deterministic(self):
        pid1 = plan_id_for("llama3", ["w2", "w1"])
        pid2 = plan_id_for("llama3", ["w1", "w2"])
        assert pid1 == pid2

    def test_different_models_differ(self):
        assert plan_id_for("llama3", ["w1"]) != plan_id_for("mistral", ["w1"])

    def test_different_workers_differ(self):
        assert plan_id_for("llama3", ["w1"]) != plan_id_for("llama3", ["w1", "w2"])
