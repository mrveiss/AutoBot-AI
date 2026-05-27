#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cross-host pipeline parallelism for sharding 70B+ models (GH#6737).

Orchestrates a multi-worker forward pass by:
  1. Discovering worker capabilities via GET /capabilities on each host.
  2. Allocating contiguous layer shards greedily by worker capacity.
  3. Chaining the forward pass: each worker receives the previous worker's
     hidden_state_out and returns its own hidden_state_out (or token_ids
     on the final worker).

Usage::

    plan = build_shard_plan(workers, total_layers)
    result = await run_pipeline(plan, model_id, input_hidden_state, session)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkerInfo:
    """Capabilities reported by a single remote NPU worker."""

    host: str  # e.g. "http://npu-worker-2:8080"
    max_layers: int
    vram_bytes_per_layer: int
    device: str = "CPU"


@dataclass
class LayerShard:
    """Assignment of a contiguous layer range to one worker."""

    worker: WorkerInfo
    layer_start: int
    layer_end: int  # inclusive
    is_last: bool = False


@dataclass
class ShardPlan:
    """Ordered list of shards that together cover all model layers."""

    shards: List[LayerShard] = field(default_factory=list)
    total_layers: int = 0

    def validate(self) -> None:
        """Raise ValueError if the plan does not cover every layer exactly once."""
        if not self.shards:
            raise ValueError("ShardPlan is empty.")
        expected = 0
        for shard in self.shards:
            if shard.layer_start != expected:
                raise ValueError(f"Gap or overlap at layer {expected}: " f"shard starts at {shard.layer_start}.")
            expected = shard.layer_end + 1
        if expected != self.total_layers:
            raise ValueError(f"Shards cover {expected} layers but model has {self.total_layers}.")


# ---------------------------------------------------------------------------
# Capability discovery
# ---------------------------------------------------------------------------


async def fetch_worker_capabilities(
    host: str,
    session: Any,
    timeout: float = 10.0,
) -> WorkerInfo:
    """Query GET /capabilities on a remote worker and return WorkerInfo.

    Args:
        host: Base URL of the worker, e.g. ``http://npu-3:8080``.
        session: An aiohttp ClientSession (or compatible) for HTTP requests.
        timeout: Request timeout in seconds.

    Returns:
        WorkerInfo populated from the worker's response.

    Raises:
        RuntimeError: When the capabilities endpoint returns an error.
    """
    url = f"{host.rstrip('/')}/capabilities"
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Worker {host} /capabilities returned {resp.status}: {text}")
            data: Dict[str, Any] = await resp.json()
    except asyncio.TimeoutError:
        raise RuntimeError(f"Worker {host} /capabilities timed out after {timeout}s.")

    return WorkerInfo(
        host=host,
        max_layers=int(data["max_layers"]),
        vram_bytes_per_layer=int(data["vram_bytes_per_layer"]),
        device=str(data.get("device", "CPU")),
    )


async def discover_workers(
    hosts: Sequence[str],
    session: Any,
    timeout: float = 10.0,
) -> List[WorkerInfo]:
    """Fetch capabilities from all hosts concurrently.

    Hosts that fail to respond are logged and excluded from the result.

    Args:
        hosts: Sequence of worker base URLs.
        session: aiohttp ClientSession.
        timeout: Per-request timeout.

    Returns:
        List of WorkerInfo for reachable workers, in the same order as *hosts*.
    """
    tasks = [fetch_worker_capabilities(h, session, timeout) for h in hosts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    workers: List[WorkerInfo] = []
    for host, result in zip(hosts, results):
        if isinstance(result, Exception):
            logger.warning("pipeline_parallel: skipping %s — %s", host, result)
        else:
            workers.append(result)

    if not workers:
        raise RuntimeError("No NPU workers responded to capability queries.")

    return workers


# ---------------------------------------------------------------------------
# Shard planning
# ---------------------------------------------------------------------------


def build_shard_plan(
    workers: Sequence[WorkerInfo],
    total_layers: int,
) -> ShardPlan:
    """Greedily assign contiguous layer shards to workers by their capacity.

    Each worker receives at most ``worker.max_layers`` consecutive layers.
    Assignment proceeds left-to-right through the model; if workers cannot
    collectively cover all layers a ValueError is raised.

    Args:
        workers: Ordered list of available workers.
        total_layers: Total number of transformer layers in the model.

    Returns:
        A validated ShardPlan.

    Raises:
        ValueError: If total worker capacity is less than total_layers.
    """
    if not workers:
        raise ValueError("No workers provided for shard planning.")
    if total_layers <= 0:
        raise ValueError(f"total_layers must be positive, got {total_layers}.")

    total_capacity = sum(w.max_layers for w in workers)
    if total_capacity < total_layers:
        raise ValueError(
            f"Workers can hold {total_capacity} layers in total but model has "
            f"{total_layers}. Add more NPU workers or reduce model size."
        )

    plan = ShardPlan(total_layers=total_layers)
    remaining = total_layers
    layer_cursor = 0

    for worker in workers:
        if remaining == 0:
            break
        assigned = min(worker.max_layers, remaining)
        plan.shards.append(
            LayerShard(
                worker=worker,
                layer_start=layer_cursor,
                layer_end=layer_cursor + assigned - 1,
                is_last=False,
            )
        )
        layer_cursor += assigned
        remaining -= assigned

    if remaining > 0:
        raise ValueError(f"Could not assign {remaining} remaining layers; " "worker list exhausted.")

    if plan.shards:
        plan.shards[-1].is_last = True

    plan.validate()
    logger.info(
        "pipeline_parallel: plan covers %d layers across %d workers",
        total_layers,
        len(plan.shards),
    )
    return plan


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


async def _forward_one_shard(
    shard: LayerShard,
    model_id: str,
    hidden_state: Any,
    session: Any,
    timeout: float = 120.0,
) -> Any:
    """POST /partial_forward to one worker and return the output.

    Args:
        shard: The layer shard to execute on its assigned worker.
        model_id: Model identifier forwarded to the worker.
        hidden_state: Input activations for this shard.
        session: aiohttp ClientSession.
        timeout: Request timeout in seconds.

    Returns:
        hidden_state_out (activations) or token_ids (list of ints) for the
        last shard.

    Raises:
        RuntimeError: On HTTP error or unexpected response shape.
    """
    url = f"{shard.worker.host.rstrip('/')}/partial_forward"
    payload = {
        "model_id": model_id,
        "layer_start": shard.layer_start,
        "layer_end": shard.layer_end,
        "is_last_worker": shard.is_last,
        "hidden_state": hidden_state,
    }

    try:
        async with session.post(url, json=payload, timeout=timeout) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(
                    f"Worker {shard.worker.host} /partial_forward "
                    f"layers {shard.layer_start}–{shard.layer_end} "
                    f"returned {resp.status}: {text}"
                )
            data: Dict[str, Any] = await resp.json()
    except asyncio.TimeoutError:
        raise RuntimeError(
            f"Worker {shard.worker.host} /partial_forward timed out after {timeout}s "
            f"(layers {shard.layer_start}–{shard.layer_end})."
        )

    if shard.is_last:
        if "token_ids" not in data:
            raise RuntimeError(
                f"Last worker {shard.worker.host} did not return 'token_ids'. " f"Got keys: {list(data.keys())}"
            )
        return data["token_ids"]

    if "hidden_state_out" not in data:
        raise RuntimeError(
            f"Worker {shard.worker.host} did not return 'hidden_state_out'. " f"Got keys: {list(data.keys())}"
        )
    return data["hidden_state_out"]


async def run_pipeline(
    plan: ShardPlan,
    model_id: str,
    input_hidden_state: Any,
    session: Any,
    *,
    shard_timeout: float = 120.0,
) -> Any:
    """Execute a full cross-host pipeline forward pass.

    Iterates through the shard plan sequentially, forwarding each worker's
    output as the next worker's input.

    Args:
        plan: Validated ShardPlan from build_shard_plan.
        model_id: Model identifier.
        input_hidden_state: Token embeddings / initial activations for the
            first layer of the model.
        session: aiohttp ClientSession shared across all shard requests.
        shard_timeout: Per-shard HTTP timeout in seconds.

    Returns:
        List of token IDs from the final worker.
    """
    plan.validate()
    hidden = input_hidden_state

    for shard in plan.shards:
        logger.debug(
            "pipeline_parallel: forwarding layers %d–%d to %s",
            shard.layer_start,
            shard.layer_end,
            shard.worker.host,
        )
        hidden = await _forward_one_shard(shard, model_id, hidden, session, shard_timeout)

    return hidden
