# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Hebbian edge reinforcement from retrieval feedback for Neural Mesh RAG (#1994, #2056)."""

import json
import logging
from datetime import datetime, timezone
from itertools import combinations
from typing import Protocol

logger = logging.getLogger(__name__)


class MeshDB(Protocol):
    """Protocol for mesh database operations required by EdgeLearner."""

    async def get_edge(self, node_a: str, node_b: str) -> dict | None: ...

    async def update_edge(self, edge_id: str, **kwargs) -> None: ...

    async def create_edge(self, from_node: str, to_node: str, **kwargs) -> None: ...

    async def get_co_access_count(self, node_a: str, node_b: str) -> int: ...

    async def update_access_count(self, node_ids: list[str]) -> None: ...


class EdgeLearner:
    """Hebbian edge reinforcement: nodes that fire together, wire together.

    Consumes rag:feedback:{date} Redis streams from Phase 1 (#2024).
    Reinforces edges between co-retrieved chunks. Creates new CO_RETRIEVED
    edges after co_access_count >= threshold.
    """

    def __init__(
        self,
        db: MeshDB,
        redis,
        ema_decay: float = 0.95,
        creation_threshold: int = 3,
        initial_weight: float = 0.3,
    ) -> None:
        self.db = db
        self.redis = redis
        self.ema_decay = ema_decay
        self.creation_threshold = creation_threshold
        self.initial_weight = initial_weight

    async def on_retrieval(self, event: dict) -> None:
        """Process a single retrieval feedback event.

        Args:
            event: Dict with keys: query_text, retrieved_chunk_ids,
                   final_ranked_ids, complexity, timestamp
        """
        ranked_ids = event.get("final_ranked_ids", [])
        if isinstance(ranked_ids, str):
            ranked_ids = json.loads(ranked_ids)

        if len(ranked_ids) < 2:
            return

        top_ids = ranked_ids[:5]

        for a, b in combinations(top_ids, 2):
            await self._reinforce_or_create(a, b)

        await self.db.update_access_count(top_ids)

    async def _reinforce_or_create(self, node_a: str, node_b: str) -> None:
        """Reinforce existing edge or create new one after threshold.

        Uses EMA update for existing edges: w = w * decay + 1.0 * (1 - decay).
        Creates a CO_RETRIEVED edge once co_access_count reaches creation_threshold.
        """
        edge = await self.db.get_edge(node_a, node_b)
        if edge:
            await self._update_existing_edge(edge)
        else:
            await self._maybe_create_edge(node_a, node_b)

    async def _update_existing_edge(self, edge: dict) -> None:
        """Apply EMA weight update and increment co_access_count."""
        new_weight = edge["weight"] * self.ema_decay + 1.0 * (1 - self.ema_decay)
        await self.db.update_edge(
            edge["id"],
            weight=new_weight,
            co_access_count=edge["co_access_count"] + 1,
        )

    async def _maybe_create_edge(self, node_a: str, node_b: str) -> None:
        """Create a CO_RETRIEVED edge if co_access_count meets threshold."""
        co_count = await self.db.get_co_access_count(node_a, node_b)
        if co_count >= self.creation_threshold:
            await self.db.create_edge(
                from_node=node_a,
                to_node=node_b,
                edge_type="CO_RETRIEVED",
                weight=self.initial_weight,
                origin="learner",
            )
            logger.info(
                "EdgeLearner: created CO_RETRIEVED edge %s -> %s (co_count=%d)",
                node_a,
                node_b,
                co_count,
            )

    async def consume_feedback_stream(self, date_key: str | None = None) -> int:
        """Consume all events from a dated feedback stream.

        Stream key: rag:feedback:{YYYY-MM-DD}

        Returns:
            Number of events processed.
        """
        if date_key is None:
            date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        stream_key = f"rag:feedback:{date_key}"
        last_id = "0-0"
        processed = 0

        while True:
            entries = await self.redis.xrange(stream_key, min=last_id, count=100)
            if not entries:
                break
            for entry_id, fields in entries:
                await self.on_retrieval(fields)
                last_id = entry_id
                processed += 1
            if len(entries) < 100:
                break

        logger.info("EdgeLearner: consumed %d events from %s", processed, stream_key)
        return processed
