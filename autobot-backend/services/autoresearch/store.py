# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoResearch Experiment Store

Issue #2597: Dual persistence — Redis for recent state/timeline queries,
ChromaDB for semantic knowledge search over experiment findings.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .config import AutoResearchConfig
from .models import Experiment, ExperimentState, ExperimentStats

logger = logging.getLogger(__name__)


class ExperimentStore:
    """Persist and query experiments across Redis and ChromaDB."""

    def __init__(self, config: Optional[AutoResearchConfig] = None):
        self.config = config or AutoResearchConfig()
        self._redis = None
        self._chromadb_collection = None

    def _redis_key(self, *parts: str) -> str:
        return ":".join([self.config.redis_prefix, *parts])

    async def _get_redis(self):
        """Lazy-init async Redis client."""
        if self._redis is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis = get_redis_client(
                async_client=True,
                database=self.config.redis_database,
            )
        return self._redis

    async def _get_chromadb(self):
        """Lazy-init ChromaDB collection."""
        if self._chromadb_collection is None:
            from utils.chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            self._chromadb_collection = await client.get_or_create_collection(
                name=self.config.chromadb_collection,
                metadata={"description": "AutoResearch experiment findings"},
            )
        return self._chromadb_collection

    async def save_experiment(
        self,
        experiment: Experiment,
        old_state: Optional[ExperimentState] = None,
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
        if experiment.result:
            parts.append(f"val_bpb: {experiment.result.val_bpb}")
            if (
                experiment.improvement is not None
                and experiment.improvement_pct is not None
            ):
                parts.append(
                    f"Improvement: {experiment.improvement:.4f} "
                    f"({experiment.improvement_pct:.2f}%)"
                )
        if experiment.code_diff:
            parts.append(f"Code change:\n{experiment.code_diff[:500]}")
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
        return meta

    async def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Retrieve a single experiment by ID."""
        redis = await self._get_redis()
        data = await redis.hget(
            self._redis_key("experiments"),
            experiment_id,
        )
        if data is None:
            return None
        return Experiment.from_dict(json.loads(data))

    async def list_experiments(
        self,
        limit: int = 50,
        offset: int = 0,
        state: Optional[ExperimentState] = None,
    ) -> List[Experiment]:
        """List experiments, most recent first."""
        redis = await self._get_redis()

        if state is not None:
            # Intersect state set with timeline for chronological ordering
            state_ids = await redis.smembers(self._redis_key("state", state.value))
            if not state_ids:
                return []
            # Score experiments by their timeline position (created_at)
            scored = []
            for eid in state_ids:
                score = await redis.zscore(self._redis_key("timeline"), eid)
                if score is not None:
                    scored.append((eid, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            experiment_ids = [eid for eid, _ in scored[offset : offset + limit]]
        else:
            experiment_ids = await redis.zrevrange(
                self._redis_key("timeline"),
                offset,
                offset + limit - 1,
            )

        experiments = []
        for eid in experiment_ids:
            exp = await self.get_experiment(
                eid if isinstance(eid, str) else eid.decode("utf-8")
            )
            if exp:
                experiments.append(exp)
        return experiments

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
        completed = await self.list_experiments(
            limit=100, state=ExperimentState.COMPLETED
        )
        kept = await self.list_experiments(limit=100, state=ExperimentState.KEPT)
        all_done = completed + kept

        if all_done:
            wall_times = [
                e.result.wall_time_seconds
                for e in all_done
                if e.result and e.result.wall_time_seconds > 0
            ]
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

    async def get_baseline(self) -> Optional[float]:
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
