# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hebbian edge reinforcement from retrieval feedback for Neural Mesh RAG (#1994, #2056)."""

import json
from datetime import datetime, timezone
from itertools import combinations
from typing import Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


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

    Cursor tracking: _cursors maps stream_key -> last consumed entry ID so
    that repeated calls to consume_feedback_stream() only read NEW entries
    instead of re-processing the entire stream from the start. Fix: #2102.

    EWC++ protection (#2097): Elastic Weight Consolidation prevents new
    retrieval feedback from overwriting high-confidence learned edge weights.
    Per-edge importance (Fisher proxy) grows with successful co-retrievals
    and dampens updates proportionally. Disabled when ewc_lambda=0.

    EWC state persistence (#2546): reference weights and importance scores
    are persisted to Redis hashes so that EWC protection survives restarts.
    update_importance() is called automatically on every successful edge
    reinforcement so that importance scores accumulate correctly over time.
    """

    # Redis hash key for persisting stream cursors across restarts (#2210).
    CURSOR_HASH_KEY = "rag:cursors:edge_learner"
    # Redis hash keys for persisting EWC++ state across restarts (#2546).
    EWC_REFERENCE_WEIGHTS_KEY = "mesh:ewc:reference_weights"
    EWC_IMPORTANCE_KEY = "mesh:ewc:importance"

    def __init__(
        self,
        db: MeshDB,
        redis,
        ema_decay: float = 0.95,
        creation_threshold: int = 3,
        initial_weight: float = 0.3,
        ewc_lambda: float = 0.4,
        ewc_consolidation_interval: int = 100,
    ) -> None:
        self.db = db
        self.redis = redis
        self.ema_decay = ema_decay
        self.creation_threshold = creation_threshold
        self.initial_weight = initial_weight
        # EWC++ parameters (#2097)
        if ewc_lambda < 0:
            raise ValueError(f"ewc_lambda must be >= 0, got {ewc_lambda}")
        self.ewc_lambda = ewc_lambda
        self.ewc_consolidation_interval = ewc_consolidation_interval
        self._update_count: int = 0
        self._reference_weights: dict[str, float] = {}
        self._importance: dict[str, float] = {}
        # Per-stream cursor: stream_key -> last processed Redis entry ID.
        # Prevents duplicate processing when the scheduler loops every second.
        # Loaded from Redis on first access (#2210).
        self._cursors: dict[str, str] = {}
        self._cursors_loaded = False
        # EWC++ state is loaded lazily from Redis on first consume call (#2546).
        self._ewc_state_loaded = False

    async def _load_cursors(self) -> None:
        """Load persisted cursors from Redis hash on first call (#2210)."""
        if self._cursors_loaded:
            return
        try:
            stored = await self.redis.hgetall(self.CURSOR_HASH_KEY)
            if stored:
                self._cursors.update(stored)
                logger.info(
                    "EdgeLearner: loaded %d persisted cursors from Redis",
                    len(stored),
                )
        except Exception:
            logger.warning("EdgeLearner: failed to load cursors, starting from 0-0")
        self._cursors_loaded = True

    async def _save_cursor(self, stream_key: str, cursor: str) -> None:
        """Persist a single cursor to Redis hash (#2210)."""
        try:
            await self.redis.hset(self.CURSOR_HASH_KEY, stream_key, cursor)
        except Exception:
            logger.warning("EdgeLearner: failed to persist cursor for %s", stream_key)

    async def _load_ewc_state(self) -> None:
        """Load persisted EWC++ reference weights and importance from Redis on first call (#2546)."""
        if self._ewc_state_loaded:
            return
        try:
            raw_weights = await self.redis.hgetall(self.EWC_REFERENCE_WEIGHTS_KEY)
            if raw_weights:
                self._reference_weights.update({k: float(v) for k, v in raw_weights.items()})
                logger.info(
                    "EdgeLearner: loaded %d persisted EWC reference weights from Redis",
                    len(raw_weights),
                )
        except Exception:
            logger.warning("EdgeLearner: failed to load EWC reference weights, starting empty")
        try:
            raw_importance = await self.redis.hgetall(self.EWC_IMPORTANCE_KEY)
            if raw_importance:
                self._importance.update({k: float(v) for k, v in raw_importance.items()})
                logger.info(
                    "EdgeLearner: loaded %d persisted EWC importance scores from Redis",
                    len(raw_importance),
                )
        except Exception:
            logger.warning("EdgeLearner: failed to load EWC importance scores, starting empty")
        self._ewc_state_loaded = True

    async def _save_ewc_state(self) -> None:
        """Persist EWC++ reference weights and importance scores to Redis (#2546)."""
        if self._reference_weights:
            try:
                await self.redis.hset(
                    self.EWC_REFERENCE_WEIGHTS_KEY,
                    mapping={k: str(v) for k, v in self._reference_weights.items()},
                )
            except Exception:
                logger.warning("EdgeLearner: failed to persist EWC reference weights")
        if self._importance:
            try:
                await self.redis.hset(
                    self.EWC_IMPORTANCE_KEY,
                    mapping={k: str(v) for k, v in self._importance.items()},
                )
            except Exception:
                logger.warning("EdgeLearner: failed to persist EWC importance scores")

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

    def _compute_ewc_penalty(self, edge_id: str, proposed_weight: float) -> float:
        """Compute EWC penalty: λ * F_i * (θ_i - θ*_i)².

        Returns 0.0 when no reference weight exists for this edge (#2097).
        """
        if not self._reference_weights or edge_id not in self._reference_weights:
            return 0.0
        ref = self._reference_weights[edge_id]
        importance = self._importance.get(edge_id, 0.0)
        return self.ewc_lambda * importance * (proposed_weight - ref) ** 2

    def _apply_ewc_dampening(self, edge_id: str, current_weight: float, proposed_weight: float) -> float:
        """Dampen weight update proportionally to EWC penalty (#2097).

        High penalty (high-importance edge) → dampening factor near 0 → minimal change.
        Zero lambda or no reference → returns proposed_weight unchanged.
        """
        if self.ewc_lambda == 0.0:
            return proposed_weight
        penalty = self._compute_ewc_penalty(edge_id, proposed_weight)
        dampening = 1.0 / (1.0 + penalty)
        return current_weight + dampening * (proposed_weight - current_weight)

    def update_importance(self, edge_id: str, success: bool) -> None:
        """Update per-edge importance based on retrieval success (#2097).

        Importance is a Fisher information proxy: grows with successful
        co-retrievals (ewma toward 1.0) and decays gently otherwise.
        """
        current = self._importance.get(edge_id, 0.0)
        if success:
            self._importance[edge_id] = current * 0.9 + 0.1
        else:
            self._importance[edge_id] = current * 0.95

    async def consolidate_weights(self) -> None:
        """Snapshot current EWC state to Redis as reference points (#2097, #2546).

        Called automatically every ewc_consolidation_interval updates.
        Persists both reference weights and importance scores so that EWC
        protection survives EdgeLearner restarts.
        """
        await self._save_ewc_state()
        logger.info(
            "EdgeLearner: consolidated %d reference weights and %d importance scores to Redis",
            len(self._reference_weights),
            len(self._importance),
        )

    async def _update_existing_edge(self, edge: dict) -> None:
        """Apply EMA weight update with EWC++ dampening and increment co_access_count (#2097, #2546)."""
        proposed_weight = edge["weight"] * self.ema_decay + 1.0 * (1 - self.ema_decay)
        final_weight = self._apply_ewc_dampening(edge["id"], edge["weight"], proposed_weight)
        await self.db.update_edge(
            edge["id"],
            weight=final_weight,
            co_access_count=edge["co_access_count"] + 1,
        )
        # Track reference weight for future EWC penalty computations.
        self._reference_weights[edge["id"]] = final_weight
        # Record successful co-retrieval so importance accumulates over time (#2546).
        self.update_importance(edge["id"], success=True)
        self._update_count += 1
        if self._update_count % self.ewc_consolidation_interval == 0:
            await self.consolidate_weights()

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
        """Consume only NEW events from a dated feedback stream. Fix: #2102.

        Uses a per-stream cursor (_cursors) to remember the last processed
        Redis entry ID so repeated calls by the scheduler do not re-process
        the same events.  Starts from the beginning only on the first call
        for a given date key.

        Stream key: rag:feedback:{YYYY-MM-DD}

        Returns:
            Number of NEW events processed in this call.
        """
        if date_key is None:
            date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        stream_key = f"rag:feedback:{date_key}"
        # Load persisted cursors and EWC state from Redis on first call (#2210, #2546).
        await self._load_cursors()
        await self._load_ewc_state()
        # Resume from exclusive lower bound. "0-0" reads from the start.
        # After processing entry "T-S", we store "T-(S+1)" so the next
        # xrange call excludes the already-processed entry.
        resume_id = self._cursors.get(stream_key, "0-0")
        processed = 0

        while True:
            entries = await self.redis.xrange(stream_key, min=resume_id, count=100)
            if not entries:
                break
            for entry_id, fields in entries:
                await self.on_retrieval(fields)
                # Advance cursor past this entry (exclusive lower bound).
                ts, seq = entry_id.split("-")
                resume_id = f"{ts}-{int(seq) + 1}"
                processed += 1
            if len(entries) < 100:
                break

        # Persist cursor only when we actually advanced past an entry.
        if processed > 0:
            self._cursors[stream_key] = resume_id
            await self._save_cursor(stream_key, resume_id)

        if processed:
            logger.info("EdgeLearner: consumed %d new events from %s", processed, stream_key)
        else:
            logger.debug("EdgeLearner: no new events in %s", stream_key)
        return processed
