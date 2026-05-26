# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
services.npu_pipeline — shard planning, caching, and cross-host pipeline dispatch.

NPU Cross-Host Pipeline Service (GH#6737 / MVA-1096/1097)

Cross-host tensor-pipeline dispatcher for models that exceed single-worker VRAM.

Public API
----------
ShardPlanner helpers:
    plan_shards(model, pool) -> List[ShardAssignment]
    plan_id_for(model_id, active_worker_ids) -> str

Data types:
    ModelDescriptor, WorkerPoolEntry, ShardAssignment, LayerRange
    InsufficientPoolError

Cache:
    RedisShardPlanCache

Invalidation:
    PlanInvalidationHandler
    get_plan_invalidation_handler()
"""

from services.npu_pipeline.invalidation import (
    PlanInvalidationHandler,
    get_plan_invalidation_handler,
)
from services.npu_pipeline.plan_cache import RedisShardPlanCache
from services.npu_pipeline.shard_planner import (
    InsufficientPoolError,
    LayerRange,
    ModelDescriptor,
    ShardAssignment,
    WorkerPoolEntry,
    plan_id_for,
    plan_shards,
)

__all__ = [
    "plan_shards",
    "plan_id_for",
    "ModelDescriptor",
    "WorkerPoolEntry",
    "ShardAssignment",
    "LayerRange",
    "InsufficientPoolError",
    "RedisShardPlanCache",
    "PlanInvalidationHandler",
    "get_plan_invalidation_handler",
]
