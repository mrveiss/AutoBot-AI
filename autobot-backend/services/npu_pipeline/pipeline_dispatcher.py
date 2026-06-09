# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
NPU Pipeline Dispatcher (GH#6737)

Splits an oversized model across multiple NPU workers, streams token generation
cross-host, and falls back to single-worker mode when workers drop mid-run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)

# GB of VRAM reported by workers in the shard plan
GB = 1024**3


class WorkerState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"


@dataclass
class WorkerNode:
    """Represents a single NPU worker participating in the pipeline."""

    worker_id: str
    vram_bytes: int
    state: WorkerState = WorkerState.ONLINE
    url: str = ""

    @property
    def vram_gb(self) -> float:
        return self.vram_bytes / GB


@dataclass
class ShardPlan:
    """Immutable assignment of model layers to workers for one inference run."""

    model_id: str
    total_params: int
    workers: List[WorkerNode]
    layers_per_worker: List[int]
    created_at: float = field(default_factory=time.monotonic)

    @property
    def worker_ids(self) -> List[str]:
        return [w.worker_id for w in self.workers]

    def is_valid(self, registry: "PipelineDispatcher") -> bool:
        """Return False if any assigned worker is no longer online."""
        current_ids = {w.worker_id for w in registry.workers if w.state == WorkerState.ONLINE}
        return all(wid in current_ids for wid in self.worker_ids)


@dataclass
class PipelineMetrics:
    """Per-inference telemetry collected across all pipeline stages."""

    hop_count: int = 0
    layer_transfer_latency_ms: float = 0.0
    per_worker_compute_ms: Dict[str, float] = field(default_factory=dict)
    fallback_fired: bool = False
    total_tokens: int = 0

    def record_hop(self, transfer_ms: float) -> None:
        self.hop_count += 1
        self.layer_transfer_latency_ms += transfer_ms

    def record_worker_compute(self, worker_id: str, compute_ms: float) -> None:
        self.per_worker_compute_ms[worker_id] = self.per_worker_compute_ms.get(worker_id, 0.0) + compute_ms


@dataclass
class PipelineResult:
    tokens: List[str]
    metrics: PipelineMetrics
    fallback_used: bool = False


class PipelineDispatcher:
    """
    Routes oversized-model inference requests across multiple NPU workers.

    Lifecycle:
    1. ``register_worker`` / ``remove_worker`` maintain the live worker pool
    2. ``plan_shards`` builds (or returns cached) a ShardPlan for a model
    3. ``run`` executes the pipeline and returns tokens + telemetry
    4. ``worker.added`` / ``worker.removed`` events invalidate the shard cache
    """

    _SHARD_CACHE_KEY_PREFIX = "npu:shard_plan:"

    def __init__(self, redis_client=None, tracing_service=None) -> None:
        self._workers: List[WorkerNode] = []
        self._shard_cache: Dict[str, ShardPlan] = {}
        self._redis = redis_client
        self._tracing = tracing_service
        self._fallback_count: int = 0
        self._run_count: int = 0

    # ------------------------------------------------------------------
    # Worker registry
    # ------------------------------------------------------------------

    @property
    def workers(self) -> List[WorkerNode]:
        return list(self._workers)

    def register_worker(self, worker: WorkerNode) -> None:
        self._workers = [w for w in self._workers if w.worker_id != worker.worker_id]
        self._workers.append(worker)
        self._invalidate_shard_cache(reason="worker.added")
        logger.info("worker.added: %s", worker.worker_id)

    def remove_worker(self, worker_id: str) -> None:
        self._workers = [w for w in self._workers if w.worker_id != worker_id]
        self._invalidate_shard_cache(reason="worker.removed")
        logger.info("worker.removed: %s", worker_id)

    def _invalidate_shard_cache(self, reason: str) -> None:
        count = len(self._shard_cache)
        self._shard_cache.clear()
        logger.debug("shard cache invalidated (%s): %d plan(s) dropped", reason, count)

    # ------------------------------------------------------------------
    # Shard planning
    # ------------------------------------------------------------------

    def plan_shards(self, model_id: str, total_params: int) -> ShardPlan:
        if model_id in self._shard_cache:
            cached = self._shard_cache[model_id]
            if cached.is_valid(self):
                return cached

        online = [w for w in self._workers if w.state == WorkerState.ONLINE]
        if not online:
            raise RuntimeError("No online workers available for pipeline dispatch")

        layers = self._distribute_layers(total_params, online)
        plan = ShardPlan(
            model_id=model_id,
            total_params=total_params,
            workers=online,
            layers_per_worker=layers,
        )
        self._shard_cache[model_id] = plan
        return plan

    @staticmethod
    def _distribute_layers(total_params: int, workers: List[WorkerNode]) -> List[int]:
        """Distribute model layers proportionally to worker VRAM."""
        total_vram = sum(w.vram_bytes for w in workers)
        layers = [max(1, round(total_params * (w.vram_bytes / total_vram))) for w in workers]
        # Ensure total sums exactly to total_params
        diff = total_params - sum(layers)
        layers[-1] += diff
        return layers

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    async def run(
        self,
        model_id: str,
        total_params: int,
        prompt: str,
        max_tokens: int = 8,
    ) -> PipelineResult:
        """
        Execute a pipeline inference run.

        Tries multi-worker dispatch; falls back to single-worker if a worker
        drops during the run.  Emits telemetry via tracing_service when present.
        """
        self._run_count += 1
        metrics = PipelineMetrics()
        plan = self.plan_shards(model_id, total_params)
        fallback_used = False

        try:
            tokens = await self._run_pipeline(plan, prompt, max_tokens, metrics)
        except WorkerDroppedError as exc:
            logger.warning(
                "Worker dropped mid-run (%s), engaging single-worker fallback",
                exc.worker_id,
            )
            self.remove_worker(exc.worker_id)
            metrics.fallback_fired = True
            self._fallback_count += 1
            fallback_used = True
            tokens = await self._run_single_worker_fallback(model_id, total_params, prompt, max_tokens, metrics)

        metrics.total_tokens = len(tokens)
        self._emit_metrics(metrics)
        return PipelineResult(tokens=tokens, metrics=metrics, fallback_used=fallback_used)

    async def _run_pipeline(
        self,
        plan: ShardPlan,
        prompt: str,
        max_tokens: int,
        metrics: PipelineMetrics,
    ) -> List[str]:
        tokens: List[str] = []
        for i, worker in enumerate(plan.workers):
            if worker.state != WorkerState.ONLINE:
                raise WorkerDroppedError(worker.worker_id)
            t0 = time.monotonic()
            chunk = await self._call_worker(worker, plan.layers_per_worker[i], prompt, max_tokens)
            compute_ms = (time.monotonic() - t0) * 1000
            metrics.record_worker_compute(worker.worker_id, compute_ms)
            tokens.extend(chunk)
            if i < len(plan.workers) - 1:
                transfer_ms = await self._simulate_layer_transfer(worker, plan.workers[i + 1])
                metrics.record_hop(transfer_ms)
        return tokens

    async def _run_single_worker_fallback(
        self,
        model_id: str,
        total_params: int,
        prompt: str,
        max_tokens: int,
        metrics: PipelineMetrics,
    ) -> List[str]:
        online = [w for w in self._workers if w.state == WorkerState.ONLINE]
        if not online:
            raise RuntimeError("No workers available for fallback")
        worker = online[0]
        t0 = time.monotonic()
        tokens = await self._call_worker(worker, total_params, prompt, max_tokens)
        compute_ms = (time.monotonic() - t0) * 1000
        metrics.record_worker_compute(worker.worker_id, compute_ms)
        return tokens

    # ------------------------------------------------------------------
    # Simulated worker calls (real impl talks to NPU worker HTTP API)
    # ------------------------------------------------------------------

    async def _call_worker(
        self,
        worker: WorkerNode,
        layer_count: int,
        prompt: str,
        max_tokens: int,
    ) -> List[str]:
        await asyncio.sleep(0)  # yield; real impl awaits HTTP response
        count = max(1, max_tokens // max(1, layer_count // 8 + 1))
        return [f"tok_{worker.worker_id}_{i}" for i in range(count)]

    async def _simulate_layer_transfer(self, src: WorkerNode, dst: WorkerNode) -> float:
        """Return simulated transfer latency in ms."""
        await asyncio.sleep(0)
        return 2.5  # nominal 2.5 ms cross-host hop

    # ------------------------------------------------------------------
    # Metrics / tracing
    # ------------------------------------------------------------------

    def _emit_metrics(self, metrics: PipelineMetrics) -> None:
        if self._tracing is None:
            return
        try:
            span = self._tracing.start_span(
                "npu_pipeline.inference",
                attributes={
                    "npu.hop_count": metrics.hop_count,
                    "npu.layer_transfer_ms": metrics.layer_transfer_latency_ms,
                    "npu.fallback_fired": metrics.fallback_fired,
                    "npu.total_tokens": metrics.total_tokens,
                    "npu.fallback_rate": self.fallback_rate,
                },
            )
            if span:
                span.end()
        except Exception:
            logger.exception("Failed to emit pipeline metrics to tracing service")

    @property
    def fallback_rate(self) -> float:
        if self._run_count == 0:
            return 0.0
        return self._fallback_count / self._run_count


class WorkerDroppedError(Exception):
    def __init__(self, worker_id: str) -> None:
        super().__init__(f"Worker {worker_id!r} dropped during pipeline run")
        self.worker_id = worker_id
