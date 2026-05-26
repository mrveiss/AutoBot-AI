# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ShardPlanner — distributes model layers across NPU workers proportional to VRAM.

Given a model descriptor and a pool of workers (each with a VRAM budget),
produces a list of ``(worker_id, layer_range)`` assignments so that every
layer is covered exactly once.  Workers with more VRAM receive proportionally
more layers.

Raises ``InsufficientPoolError`` when the pool cannot cover the model at all.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class InsufficientPoolError(Exception):
    """Raised when no enabled workers are available to host the model."""


@dataclass(frozen=True)
class LayerRange:
    """Closed-interval layer assignment [start, end]."""

    start: int
    end: int

    @property
    def count(self) -> int:
        return self.end - self.start + 1

    def __repr__(self) -> str:
        return f"[{self.start}-{self.end}]"


@dataclass(frozen=True)
class ShardAssignment:
    """Single worker → layer-range binding."""

    worker_id: str
    layer_range: LayerRange


@dataclass
class ModelDescriptor:
    """Minimal model description needed for shard planning."""

    model_id: str
    total_layers: int
    bytes_per_layer: int = 0


@dataclass
class WorkerPoolEntry:
    """A single worker's identity and available VRAM."""

    worker_id: str
    vram_bytes: int
    enabled: bool = True


def plan_shards(
    model: ModelDescriptor,
    pool: List[WorkerPoolEntry],
) -> List[ShardAssignment]:
    """Produce a layer-distribution plan for *model* across *pool*.

    Layers are distributed proportional to each worker's VRAM.  Rounding
    errors are given to the first worker.  A single-worker pool receives
    the full layer range.

    Args:
        model: Model to shard.
        pool: Workers to consider; disabled workers are skipped.

    Returns:
        Ordered list of ``ShardAssignment`` items covering all layers.

    Raises:
        InsufficientPoolError: If no enabled workers exist.
    """
    active = [w for w in pool if w.enabled and w.vram_bytes > 0]
    if not active:
        raise InsufficientPoolError(f"No enabled workers with VRAM available for model '{model.model_id}'")

    total_layers = model.total_layers
    if total_layers <= 0:
        raise ValueError(f"model.total_layers must be > 0, got {total_layers}")

    # Single-worker fast path
    if len(active) == 1:
        return [
            ShardAssignment(
                worker_id=active[0].worker_id,
                layer_range=LayerRange(0, total_layers - 1),
            )
        ]

    total_vram = sum(w.vram_bytes for w in active)
    shares: List[int] = []
    for w in active:
        share = math.floor(total_layers * w.vram_bytes / total_vram)
        shares.append(max(share, 0))

    # Distribute remainder to first worker
    remainder = total_layers - sum(shares)
    if remainder > 0:
        shares[0] += remainder

    assignments: List[ShardAssignment] = []
    cursor = 0
    for worker, layer_count in zip(active, shares):
        if layer_count == 0:
            # Edge case: worker got zero layers; give it at least one
            # (only reachable when total_layers < len(active))
            layer_count = 1
        end = min(cursor + layer_count - 1, total_layers - 1)
        assignments.append(
            ShardAssignment(
                worker_id=worker.worker_id,
                layer_range=LayerRange(cursor, end),
            )
        )
        cursor = end + 1
        if cursor >= total_layers:
            break

    logger.debug(
        "ShardPlanner: model=%s layers=%d workers=%d assignments=%s",
        model.model_id,
        total_layers,
        len(active),
        [(a.worker_id, repr(a.layer_range)) for a in assignments],
    )
    return assignments


def plan_id_for(model_id: str, active_worker_ids: List[str]) -> str:
    """Deterministic plan ID derived from model + sorted worker set."""
    worker_key = ",".join(sorted(active_worker_ids))
    return f"{model_id}::{worker_key}"
