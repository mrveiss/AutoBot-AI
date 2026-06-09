# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoResearch Experiment Store

Issue #2597: Dual persistence — Redis for recent state/timeline queries,
ChromaDB for semantic knowledge search over experiment findings.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

from .config import AutoResearchConfig
from .models import Experiment, ExperimentState, ExperimentStats

logger = get_logger(__name__)


class ExperimentStore(AsyncRedisClientMixin):
    """Persist and query experiments across Redis and ChromaDB."""

    def __init__(self, config: AutoResearchConfig | None = None) -> None:
        self.config = config or AutoResearchConfig()
        self._redis_database = self.config.redis_database
        self._chromadb_collection = None

    def _redis_key(self, *parts: str) -> str:
        return ":".join([self.config.redis_prefix, *parts])

    async def _get_chromadb(self):
        """Lazy-init ChromaDB collection."""
        if self._chromadb_collection is None:
            from knowledge.backends import get_async_default_client

            client = await get_async_default_client()
            self._chromadb_collection = await client.get_or_create_collection(
                name=self.config.chromadb_collection,
                metadata={"description": "AutoResearch experiment findings"},
            )
        return self._chromadb_collection

    async def save_experiment(
        self,
        experiment: Experiment,
        old_state: ExperimentState | None = None,
    ) -> None:
        """Persist experiment to Redis (always) and ChromaDB (if completed)."""
        redis = await self._get_redis()
        data = json.dumps(experiment.to_dict())

        # Store in hash keyed by experiment ID
        await redis.hset(
            self._redis_key("experiments"),
            experiment.id,
            data,
        )

        # Add to sorted set for timeline queries (score = created_at)
        await redis.zadd(
            self._redis_key("timeline"),
            {experiment.id: experiment.created_at},
        )

        # Clean up old state index before adding to new one
        if old_state is not None and old_state != experiment.state:
            await redis.srem(
                self._redis_key("state", old_state.value),
                experiment.id,
            )

        # Update state index
        await redis.sadd(
            self._redis_key("state", experiment.state.value),
            experiment.id,
        )

        # Track best val_bpb
        if experiment.result and experiment.result.val_bpb is not None:
            current_best = await redis.get(self._redis_key("best_val_bpb"))
            if current_best is None or experiment.result.val_bpb < float(current_best):
                await redis.set(
                    self._redis_key("best_val_bpb"),
                    str(experiment.result.val_bpb),
                )

        # Index completed experiments in ChromaDB for semantic search
        if experiment.state in (ExperimentState.COMPLETED, ExperimentState.KEPT):
            await self._index_in_chromadb(experiment)

        logger.info(
            "Saved experiment %s (state=%s)",
            experiment.id,
            experiment.state.value,
        )

    async def _index_in_chromadb(self, experiment: Experiment) -> None:
        """Index experiment findings in ChromaDB for future RAG queries."""
        try:
            collection = await self._get_chromadb()
            document = self._build_document(experiment)
            metadata = self._build_metadata(experiment)

            await collection.upsert(
                ids=[experiment.id],
                documents=[document],
                metadatas=[metadata],
            )
            logger.info("Indexed experiment %s in ChromaDB", experiment.id)
        except Exception:
            logger.exception(
                "Failed to index experiment %s in ChromaDB",
                experiment.id,
            )

    def _build_document(self, experiment: Experiment) -> str:
        """Build a searchable text document from experiment data."""
        parts = [
            f"Hypothesis: {experiment.hypothesis}",
            f"Description: {experiment.description}",
        ]
        # Include hyperparams for richer search
        hp_dict = experiment.hyperparams.to_dict()
        parts.append(f"Hyperparams: {', '.join(f'{k}={v}' for k, v in hp_dict.items())}")

        if experiment.result:
            parts.append(f"val_bpb: {experiment.result.val_bpb}")
            if experiment.baseline_val_bpb is not None and experiment.result.val_bpb is not None:
                improvement = experiment.baseline_val_bpb - experiment.result.val_bpb
                pct = (improvement / experiment.baseline_val_bpb * 100) if experiment.baseline_val_bpb != 0 else 0
                parts.append(
                    f"Baseline: {experiment.baseline_val_bpb}, " f"Improvement: {improvement:.4f} ({pct:.2f}%)"
                )
        if experiment.code_diff:
            parts.append(f"Code change:\n{experiment.code_diff[:500]}")
        # Session context from tags
        session_tags = [t for t in experiment.tags if t.startswith("session:")]
        if session_tags:
            parts.append(f"Session: {session_tags[0].split(':', 1)[1]}")
        # Iteration number within the session
        iteration_tags = [t for t in experiment.tags if t.startswith("iteration:")]
        if iteration_tags:
            parts.append(f"Iteration: {iteration_tags[0].split(':', 1)[1]}")
        # Prior results trend direction
        trend_tags = [t for t in experiment.tags if t.startswith("trend:")]
        if trend_tags:
            parts.append(f"Trend: {trend_tags[0].split(':', 1)[1]}")
        # Prompt variant ID when optimizer is active
        variant_tags = [t for t in experiment.tags if t.startswith("variant:")]
        if variant_tags:
            parts.append(f"Variant: {variant_tags[0].split(':', 1)[1]}")
        return "\n".join(parts)

    def _build_metadata(self, experiment: Experiment) -> Dict[str, Any]:
        """Build ChromaDB metadata for filtering."""
        meta: Dict[str, Any] = {
            "state": experiment.state.value,
            "created_at": experiment.created_at,
        }
        if experiment.result and experiment.result.val_bpb is not None:
            meta["val_bpb"] = experiment.result.val_bpb
        if experiment.improvement is not None:
            meta["improvement"] = experiment.improvement
        if experiment.tags:
            meta["tags"] = ",".join(experiment.tags)
        # Include key hyperparams for filtering
        hp_dict = experiment.hyperparams.to_dict()
        for key in ("learning_rate", "dropout", "batch_size", "n_layer", "n_head"):
            if key in hp_dict:
                meta[key] = hp_dict[key]
        # Extract session ID from tags
        for tag in experiment.tags:
            if tag.startswith("session:"):
                meta["session_id"] = tag.split(":", 1)[1]
                break
        # Extract iteration number from tags
        for tag in experiment.tags:
            if tag.startswith("iteration:"):
                raw = tag.split(":", 1)[1]
                try:
                    meta["iteration"] = int(raw)
                except ValueError:
                    pass
                break
        # Extract trend direction from tags
        for tag in experiment.tags:
            if tag.startswith("trend:"):
                meta["trend_direction"] = tag.split(":", 1)[1]
                break
        # Extract prompt variant ID from tags
        for tag in experiment.tags:
            if tag.startswith("variant:"):
                meta["variant_id"] = tag.split(":", 1)[1]
                break
        return meta

    async def get_experiment(self, experiment_id: str) -> Experiment | None:
        """Retrieve a single experiment by ID."""
        redis = await self._get_redis()
        data = await redis.hget(
            self._redis_key("experiments"),
            experiment_id,
        )
        if data is None:
            return None
        return Experiment.from_dict(json.loads(data))

    async def _fetch_experiments_by_ids(self, experiment_ids: List[str]) -> List[Experiment]:
        """Batch-fetch experiments from Redis using a single HMGET call.

        Replaces N individual HGET calls with one pipeline command — see #2684.
        """
        if not experiment_ids:
            return []
        redis = await self._get_redis()
        raw_values = await redis.hmget(self._redis_key("experiments"), *experiment_ids)
        experiments = []
        for raw in raw_values:
            if raw is not None:
                experiments.append(Experiment.from_dict(json.loads(raw)))
        return experiments

    async def _sorted_ids_for_state(self, redis, state: ExperimentState, limit: int, offset: int) -> List[str]:
        """Return experiment IDs for *state*, ordered newest-first, with paging.

        Uses a single pipeline to batch all ZSCORE calls — see #2684.
        """
        state_ids = await redis.smembers(self._redis_key("state", state.value))
        if not state_ids:
            return []

        timeline_key = self._redis_key("timeline")
        pipe = redis.pipeline()
        id_list = [eid if isinstance(eid, str) else eid.decode("utf-8") for eid in state_ids]
        for eid in id_list:
            pipe.zscore(timeline_key, eid)
        scores = await pipe.execute()

        scored = [(eid, sc) for eid, sc in zip(id_list, scores) if sc is not None]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [eid for eid, _ in scored[offset : offset + limit]]

    async def list_experiments(
        self,
        limit: int = 50,
        offset: int = 0,
        state: ExperimentState | None = None,
    ) -> List[Experiment]:
        """List experiments, most recent first."""
        redis = await self._get_redis()

        if state is not None:
            experiment_ids = await self._sorted_ids_for_state(redis, state, limit, offset)
        else:
            experiment_ids = await redis.zrevrange(
                self._redis_key("timeline"),
                offset,
                offset + limit - 1,
            )
            experiment_ids = [eid if isinstance(eid, str) else eid.decode("utf-8") for eid in experiment_ids]

        return await self._fetch_experiments_by_ids(experiment_ids)

    async def get_stats(self) -> ExperimentStats:
        """Compute aggregate statistics across all experiments."""
        redis = await self._get_redis()
        stats = ExperimentStats()

        stats.total_experiments = await redis.hlen(self._redis_key("experiments"))

        for state_name in ("completed", "failed", "kept", "discarded"):
            count = await redis.scard(self._redis_key("state", state_name))
            setattr(stats, state_name, count)

        best = await redis.get(self._redis_key("best_val_bpb"))
        if best is not None:
            stats.best_val_bpb = float(best)

        baseline = await redis.get(self._redis_key("baseline_val_bpb"))
        if baseline is not None:
            stats.baseline_val_bpb = float(baseline)

        # Compute timing stats from completed experiments
        completed, kept = await asyncio.gather(
            self.list_experiments(limit=100, state=ExperimentState.COMPLETED),
            self.list_experiments(limit=100, state=ExperimentState.KEPT),
        )
        all_done = completed + kept

        if all_done:
            wall_times = [e.result.wall_time_seconds for e in all_done if e.result and e.result.wall_time_seconds > 0]
            if wall_times:
                stats.avg_wall_time = sum(wall_times) / len(wall_times)
                stats.total_wall_time = sum(wall_times)

            stats.improvement_trend = [
                e.result.val_bpb
                for e in sorted(all_done, key=lambda x: x.created_at)
                if e.result and e.result.val_bpb is not None
            ]

        return stats

    async def set_baseline(self, val_bpb: float) -> None:
        """Record the baseline val_bpb for improvement comparison."""
        redis = await self._get_redis()
        await redis.set(
            self._redis_key("baseline_val_bpb"),
            str(val_bpb),
        )
        logger.info("Baseline val_bpb set to %s", val_bpb)

    async def get_baseline(self) -> float | None:
        """Get the current baseline val_bpb."""
        redis = await self._get_redis()
        val = await redis.get(self._redis_key("baseline_val_bpb"))
        return float(val) if val is not None else None

    async def update_experiment_state(
        self,
        experiment_id: str,
        old_state: ExperimentState,
        new_state: ExperimentState,
    ) -> None:
        """Move experiment between state indices."""
        redis = await self._get_redis()
        await redis.srem(
            self._redis_key("state", old_state.value),
            experiment_id,
        )
        await redis.sadd(
            self._redis_key("state", new_state.value),
            experiment_id,
        )
