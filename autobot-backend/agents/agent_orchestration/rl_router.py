# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Q-Learning Reinforcement Router (Issue #2092)

Sits between pattern-match routing (confidence > 0.8) and the LLM fallback
(confidence <= 0.6).  Learns optimal agent selection from task outcomes via a
tabular Q-learning update rule, with epsilon-greedy exploration that decays
towards exploitation over time.

Redis layout
------------
rl:router:qtable:{state_key}   HASH  agent_id -> Q-value (float as string)
rl:router:epsilon              STRING  current epsilon (float as string)
rl:router:step_count           STRING  total steps seen (int as string)
rl:router:replay:{state_key}   LIST   JSON-encoded (action, reward) pairs
"""

import hashlib
import json
import time
from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Redis key templates
_KEY_QTABLE = "rl:router:qtable:{state}"
_KEY_EPSILON = "rl:router:epsilon"
_KEY_STEPS = "rl:router:step_count"
_KEY_REPLAY = "rl:router:replay:{state}"

# Q-learning hyper-parameters
_ALPHA = 0.1  # Learning rate
_GAMMA = 0.9  # Discount factor (single-step; effectively unused but kept for extension)
_EPSILON_START = 1.0  # Initial exploration rate
_EPSILON_MIN = 0.05  # Floor for exploration
_EPSILON_DECAY = 0.995  # Multiplicative decay per step (cosine-like overall shape)

# Replay buffer
_REPLAY_MAX_LEN = 200  # Maximum transitions stored per state
_REPLAY_BATCH = 16  # Transitions sampled for replay update

# Confidence mapping
_CONFIDENCE_SCALE = 0.4  # Maps Q-value range [0, 1] → confidence [0.6, 1.0]
_CONFIDENCE_BASE = 0.6

# Keywords used for state hashing (domain signal extraction)
_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "code": ["code", "function", "implement", "algorithm", "class", "debug"],
    "data": ["data", "analysis", "statistics", "dataset", "correlation", "metrics"],
    "research": ["research", "search", "find", "latest", "current", "online"],
    "knowledge": ["document", "according", "summarize", "analyze", "knowledge"],
    "translate": [
        "translate",
        "translation",
        "spanish",
        "french",
        "german",
        "language",
    ],
    "summarize": ["summarize", "summary", "brief", "overview", "tldr"],
    "sentiment": ["sentiment", "opinion", "feeling", "emotion", "tone"],
    "image": ["image", "picture", "photo", "visual", "diagram"],
    "audio": ["audio", "sound", "speech", "voice", "recording"],
    "system": ["run", "execute", "command", "shell", "terminal", "system"],
    "chat": ["hello", "hi", "thanks", "what is", "explain", "help"],
}

# Length buckets for state hashing
_LENGTH_BUCKETS = [(10, "short"), (30, "medium"), (60, "long")]


class RLRouter(AsyncRedisClientMixin):
    """
    Tabular Q-learning router for agent task routing.

    Usage::

        router = RLRouter()
        agent_id, confidence = await router.select_agent(query, available_agents)
        # ... run task ...
        await router.record_outcome(state_key, agent_id, reward)

    The ``state_key`` returned from :meth:`select_agent` is stored in the
    routing result so the caller can pass it back to :meth:`record_outcome`.
    """

    _redis_database = "main"

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def select_agent(
        self,
        query: str,
        available_agents: List[str],
    ) -> Tuple[str, float, str]:
        """Choose an agent for *query* using epsilon-greedy Q-learning.

        Args:
            query: Raw user request text.
            available_agents: Agent IDs eligible for selection.

        Returns:
            Tuple of (agent_id, confidence, state_key).
            ``state_key`` must be forwarded to :meth:`record_outcome`.
        """
        if not available_agents:
            raise ValueError("available_agents must be non-empty")

        state_key = self._hash_state(query)
        epsilon = await self._get_epsilon()

        import random

        if random.random() < epsilon:  # nosec B311 - RL epsilon-greedy exploration, not cryptographic
            agent_id = random.choice(available_agents)  # nosec B311 - non-crypto random selection for RL
            logger.debug("RL explore: state=%s agent=%s eps=%.3f", state_key, agent_id, epsilon)
        else:
            agent_id = await self._greedy_select(state_key, available_agents)
            logger.debug("RL exploit: state=%s agent=%s eps=%.3f", state_key, agent_id, epsilon)

        confidence = await self._agent_confidence(state_key, agent_id)
        await self._decay_epsilon()
        return agent_id, confidence, state_key

    async def record_outcome(
        self,
        state_key: str,
        action: str,
        reward: float,
    ) -> None:
        """Update Q-table with observed reward and run experience replay.

        Args:
            state_key: State identifier returned by :meth:`select_agent`.
            action: Agent ID that was used.
            reward: Scalar reward in [0.0, 1.0] — 1.0 = perfect, 0.0 = failure.
        """
        await self._q_update(state_key, action, reward)
        await self._store_replay(state_key, action, reward)
        await self._replay_update(state_key)

    # ------------------------------------------------------------------
    # State hashing
    # ------------------------------------------------------------------

    def _hash_state(self, query: str) -> str:
        """Produce a short state key from query features.

        Features:
        - Detected domain keywords (sorted, deduplicated)
        - Query length bucket
        - 3-gram character hash of the first 80 chars (4 hex chars)
        """
        query_lower = query.lower()
        domains = sorted({domain for domain, kws in _DOMAIN_KEYWORDS.items() if any(kw in query_lower for kw in kws)})
        length_label = "xlong"
        word_count = len(query.split())
        for threshold, label in _LENGTH_BUCKETS:
            if word_count <= threshold:
                length_label = label
                break

        ngram_hash = self._ngram_hash(query_lower[:80])
        parts = ["_".join(domains) if domains else "generic", length_label, ngram_hash]
        return ":".join(parts)

    @staticmethod
    def _ngram_hash(text: str, n: int = 3) -> str:
        """Compute a 4-hex-char hash of the character n-grams of *text*."""
        ngrams = [text[i : i + n] for i in range(max(0, len(text) - n + 1))]
        raw = " ".join(ngrams).encode("utf-8")
        return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:4]  # noqa: S324 — not used for security

    # ------------------------------------------------------------------
    # Q-table operations
    # ------------------------------------------------------------------

    async def _q_get(self, state_key: str, action: str) -> float:
        """Retrieve Q(state, action), defaulting to 0.5 (optimistic init)."""
        try:
            redis = await self._get_redis()
            key = _KEY_QTABLE.format(state=state_key)
            raw = await redis.hget(key, action)
            return float(raw) if raw is not None else 0.5
        except Exception as exc:
            logger.debug("RL Q-get failed: %s", exc)
            return 0.5

    async def _q_set(self, state_key: str, action: str, value: float) -> None:
        """Persist Q(state, action)."""
        try:
            redis = await self._get_redis()
            key = _KEY_QTABLE.format(state=state_key)
            await redis.hset(key, action, str(value))
        except Exception as exc:
            logger.debug("RL Q-set failed: %s", exc)

    async def _q_update(self, state_key: str, action: str, reward: float) -> None:
        """Single-step Q-learning update: Q += alpha * (reward - Q)."""
        q_old = await self._q_get(state_key, action)
        q_new = q_old + _ALPHA * (reward - q_old)
        q_new = max(0.0, min(1.0, q_new))
        await self._q_set(state_key, action, q_new)
        logger.debug(
            "RL update: state=%s action=%s Q %.3f->%.3f (reward=%.2f)",
            state_key,
            action,
            q_old,
            q_new,
            reward,
        )

    async def _greedy_select(self, state_key: str, agents: List[str]) -> str:
        """Return agent with highest Q-value; break ties randomly."""
        import random

        try:
            redis = await self._get_redis()
            key = _KEY_QTABLE.format(state=state_key)
            raw_all = await redis.hgetall(key)
            q_map = {k.decode() if isinstance(k, bytes) else k: float(v) for k, v in raw_all.items()}
        except Exception as exc:
            logger.debug("RL greedy-select Redis error: %s", exc)
            q_map = {}

        best_q = -1.0
        best_agents: List[str] = []
        for agent in agents:
            q = q_map.get(agent, 0.5)
            if q > best_q:
                best_q = q
                best_agents = [agent]
            elif q == best_q:
                best_agents.append(agent)
        return random.choice(best_agents)  # nosec B311 - RL tie-breaking selection, not cryptographic

    async def _agent_confidence(self, state_key: str, agent_id: str) -> float:
        """Map Q-value to confidence in [0.6, 1.0]."""
        q = await self._q_get(state_key, agent_id)
        return _CONFIDENCE_BASE + _CONFIDENCE_SCALE * q

    # ------------------------------------------------------------------
    # Epsilon management
    # ------------------------------------------------------------------

    async def _get_epsilon(self) -> float:
        """Read current epsilon from Redis, falling back to start value."""
        try:
            redis = await self._get_redis()
            raw = await redis.get(_KEY_EPSILON)
            return float(raw) if raw is not None else _EPSILON_START
        except Exception as exc:
            logger.debug("RL epsilon-get failed: %s", exc)
            return _EPSILON_START

    async def _decay_epsilon(self) -> None:
        """Decay epsilon by the configured factor, respecting the floor."""
        try:
            redis = await self._get_redis()
            current = await self._get_epsilon()
            step_raw = await redis.get(_KEY_STEPS)
            steps = int(step_raw) + 1 if step_raw is not None else 1
            # Cosine-shaped decay via multiplicative step
            new_eps = max(_EPSILON_MIN, current * _EPSILON_DECAY)
            await redis.set(_KEY_EPSILON, str(new_eps))
            await redis.set(_KEY_STEPS, str(steps))
        except Exception as exc:
            logger.debug("RL epsilon-decay failed: %s", exc)

    # ------------------------------------------------------------------
    # Experience replay
    # ------------------------------------------------------------------

    async def _store_replay(self, state_key: str, action: str, reward: float) -> None:
        """Append transition to the per-state replay buffer (capped at max)."""
        try:
            redis = await self._get_redis()
            key = _KEY_REPLAY.format(state=state_key)
            entry = json.dumps({"action": action, "reward": reward, "ts": time.time()})
            await redis.lpush(key, entry)
            await redis.ltrim(key, 0, _REPLAY_MAX_LEN - 1)
        except Exception as exc:
            logger.debug("RL replay-store failed: %s", exc)

    async def _replay_update(self, state_key: str) -> None:
        """Sample past transitions and apply Q-updates (experience replay)."""
        try:
            redis = await self._get_redis()
            key = _KEY_REPLAY.format(state=state_key)
            raw_entries = await redis.lrange(key, 0, _REPLAY_BATCH - 1)
        except Exception as exc:
            logger.debug("RL replay-fetch failed: %s", exc)
            return

        for raw in raw_entries:
            try:
                entry = json.loads(raw)
                await self._q_update(state_key, entry["action"], entry["reward"])
            except Exception as exc:
                logger.debug("RL replay-update entry failed: %s", exc)

    # ------------------------------------------------------------------
    # Admin helpers (testing / monitoring)
    # ------------------------------------------------------------------

    async def reset_epsilon(self, value: float = _EPSILON_START) -> None:
        """Reset epsilon to *value* (useful for testing or kill-switch reset)."""
        try:
            redis = await self._get_redis()
            await redis.set(_KEY_EPSILON, str(value))
            await redis.set(_KEY_STEPS, "0")
        except Exception as exc:
            logger.warning("RL reset-epsilon failed: %s", exc)

    async def get_q_table_snapshot(self, state_key: str) -> Dict[str, float]:
        """Return the full Q-table for *state_key* (for monitoring/debug)."""
        try:
            redis = await self._get_redis()
            key = _KEY_QTABLE.format(state=state_key)
            raw = await redis.hgetall(key)
            return {k.decode() if isinstance(k, bytes) else k: float(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("RL q-table-snapshot failed: %s", exc)
            return {}
