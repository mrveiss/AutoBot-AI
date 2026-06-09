#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session-Adaptive Reranker — Issue #4690.

Tracks retrieval hit/miss signals within a single conversation session and
incrementally adjusts hybrid reranking weights (semantic vs keyword) so that
subsequent queries in the same session benefit from what worked earlier.

Design constraints:
- Session-local only: state is keyed by session_id, never written to Redis.
- Reset at session end: call ``end_session()`` to discard accumulated state.
- No cross-session bleed: distinct session_ids are fully independent.
- Feature-flagged: callers must check ``RAGConfig.enable_session_adaptive_reranking``
  before using this module.
- All public methods are synchronous (no I/O) for zero latency overhead.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Clamp bounds for adapted weights to prevent degenerate extremes.
_MIN_WEIGHT = 0.1
_MAX_WEIGHT = 0.9

# Learning rate: fraction of gap between current weight and target shifted per
# positive signal.  Low value (0.1) keeps adaptation gradual.
_LEARNING_RATE = 0.1

# Evict sessions that have not been accessed for this many seconds (1 hour).
SESSION_TTL_SECONDS = 3600

# Minimum interval between eviction sweeps to avoid O(n) scan on every request.
_EVICTION_INTERVAL = 60.0


@dataclass
class _SessionState:
    """Per-session weight adaptation state."""

    # Running estimates of signal quality for semantic vs keyword paths.
    semantic_hits: int = 0
    semantic_misses: int = 0
    keyword_hits: int = 0
    keyword_misses: int = 0

    # Adapted weights (initialised from RAGConfig defaults at session creation).
    hybrid_weight_semantic: float = 0.75
    hybrid_weight_keyword: float = 0.25

    # Monotonic timestamp of the last access; used for TTL-based eviction.
    last_updated: float = field(default_factory=time.monotonic)

    # Lock guards mutations from concurrent async calls on the same session.
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionAdaptiveReranker:
    """Manages per-session reranking weight adaptation.

    Instantiate once (e.g. as a RAGService attribute) and share across
    requests for the same process.  Each ``session_id`` has independent state.

    Usage::

        adapter = SessionAdaptiveReranker(
            default_semantic=config.hybrid_weight_semantic,
            default_keyword=config.hybrid_weight_keyword,
        )

        # At search time — get adapted weights for this session:
        sem, kw = adapter.get_weights(session_id)

        # After results are returned and a success signal arrives:
        adapter.record_signal(session_id, semantic_success=True, keyword_success=False)

        # Session over:
        adapter.end_session(session_id)
    """

    def __init__(
        self,
        default_semantic: float = 0.75,
        default_keyword: float = 0.25,
    ) -> None:
        self._default_semantic = default_semantic
        self._default_keyword = default_keyword
        # session_id → _SessionState
        self._sessions: Dict[str, _SessionState] = {}
        self._registry_lock = threading.Lock()
        self._last_eviction: float = 0.0  # monotonic timestamp of last eviction run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_weights(self, session_id: str) -> tuple:
        """Return (semantic_weight, keyword_weight) for this session.

        Creates default state for new sessions.  Evicts stale sessions at most
        once per 60 seconds (_EVICTION_INTERVAL).  Thread-safe.

        Returns:
            Tuple[float, float] — normalised to sum ≤ 1.0, each in [0.1, 0.9].
        """
        if time.monotonic() - self._last_eviction >= _EVICTION_INTERVAL:
            self._evict_stale_sessions()
        state = self._get_or_create(session_id)
        with state.lock:
            state.last_updated = time.monotonic()
            return state.hybrid_weight_semantic, state.hybrid_weight_keyword

    def record_signal(
        self,
        session_id: str,
        *,
        semantic_success: bool,
        keyword_success: bool,
    ) -> None:
        """Record a retrieval success/miss signal for this session.

        Adjusts session weights towards the path that succeeded.  If both or
        neither path succeeded, weights are nudged symmetrically (no change
        in ratio).  Thread-safe.

        Args:
            session_id:       Conversation/session identifier.
            semantic_success: True if the semantic path produced useful results.
            keyword_success:  True if the keyword path produced useful results.
        """
        state = self._get_or_create(session_id)
        with state.lock:
            if semantic_success:
                state.semantic_hits += 1
            else:
                state.semantic_misses += 1

            if keyword_success:
                state.keyword_hits += 1
            else:
                state.keyword_misses += 1

            state.last_updated = time.monotonic()
            self._recompute_weights(state)

        logger.debug(
            "SessionAdaptiveReranker[%s]: sem_hits=%d sem_misses=%d " "kw_hits=%d kw_misses=%d → sem=%.3f kw=%.3f",
            session_id,
            state.semantic_hits,
            state.semantic_misses,
            state.keyword_hits,
            state.keyword_misses,
            state.hybrid_weight_semantic,
            state.hybrid_weight_keyword,
        )

    def end_session(self, session_id: str) -> None:
        """Discard all accumulated state for this session.

        No-op if the session was never created.  Thread-safe.
        """
        with self._registry_lock:
            self._sessions.pop(session_id, None)
        logger.debug("SessionAdaptiveReranker: session %s ended and cleared", session_id)

    def active_session_count(self) -> int:
        """Return the number of sessions currently tracked."""
        with self._registry_lock:
            return len(self._sessions)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_stale_sessions(self) -> None:
        """Remove sessions that have not been accessed within SESSION_TTL_SECONDS."""
        cutoff = time.monotonic() - SESSION_TTL_SECONDS
        with self._registry_lock:
            stale = [sid for sid, sw in self._sessions.items() if sw.last_updated < cutoff]
            for sid in stale:
                del self._sessions[sid]
            self._last_eviction = time.monotonic()
        if stale:
            logger.debug("SessionAdaptiveReranker: evicted %d stale session(s)", len(stale))

    def _get_or_create(self, session_id: str) -> _SessionState:
        with self._registry_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = _SessionState(
                    hybrid_weight_semantic=self._default_semantic,
                    hybrid_weight_keyword=self._default_keyword,
                )
            return self._sessions[session_id]

    @staticmethod
    def _recompute_weights(state: _SessionState) -> None:
        """Update state.hybrid_weight_* from accumulated hit/miss counts.

        Uses a simple success-rate ratio: the semantic target weight is
        proportional to its success rate relative to the total success rate.
        Falls back to retaining current weights when no successes observed.

        The new weight is blended with the current weight at ``_LEARNING_RATE``
        to avoid abrupt jumps.
        """
        sem_total = state.semantic_hits + state.semantic_misses
        kw_total = state.keyword_hits + state.keyword_misses
        sem_rate = state.semantic_hits / sem_total if sem_total > 0 else 0.5
        kw_rate = state.keyword_hits / kw_total if kw_total > 0 else 0.5

        total_rate = sem_rate + kw_rate
        if total_rate <= 0.0:
            # No signal at all — keep current weights unchanged.
            return

        # Target proportional split based on success rates.
        target_sem = sem_rate / total_rate  # in [0, 1]

        # Blend towards target at learning rate.
        new_sem = state.hybrid_weight_semantic + _LEARNING_RATE * (target_sem - state.hybrid_weight_semantic)

        # Clamp and normalise.
        new_sem = max(_MIN_WEIGHT, min(_MAX_WEIGHT, new_sem))
        new_kw = max(_MIN_WEIGHT, min(_MAX_WEIGHT, 1.0 - new_sem))

        state.hybrid_weight_semantic = new_sem
        state.hybrid_weight_keyword = new_kw


# Module-level registry: one adapter per (default_semantic, default_keyword) pair.
# RAGService creates its own instance via _get_session_adaptive_reranker().
_reranker_cache: Dict[tuple, SessionAdaptiveReranker] = {}
_reranker_cache_lock = threading.Lock()


def get_session_adaptive_reranker(
    default_semantic: float = 0.75,
    default_keyword: float = 0.25,
) -> SessionAdaptiveReranker:
    """Return a cached ``SessionAdaptiveReranker`` for the given defaults.

    Keyed by (default_semantic, default_keyword) so distinct RAGConfig
    instances with different defaults each get their own adapter without
    unnecessary object creation.
    """
    key = (default_semantic, default_keyword)
    with _reranker_cache_lock:
        if key not in _reranker_cache:
            _reranker_cache[key] = SessionAdaptiveReranker(
                default_semantic=default_semantic,
                default_keyword=default_keyword,
            )
        return _reranker_cache[key]
