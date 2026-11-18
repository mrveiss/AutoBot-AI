# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RAGService learning hooks (#21606): the retrieval-pattern lookup/outcome and the session-adaptive
reranking signal, split out of ``rag_service`` along the mixin pattern of ``rag_cache_tiers``.
Behaviour is unchanged by the split.
"""

from typing import List

from advanced_rag_optimizer import RankedResult
from autobot_shared.logging_manager import get_llm_logger
from knowledge.search_components.retrieval_learner import get_retrieval_learner

logger = get_llm_logger("rag_service")


class RAGLearningMixin:
    """The learning hooks of ``RAGService``; relies on its ``_session_reranker``."""

    async def _lookup_retrieval_pattern(
        self,
        query: str,
        complexity: str,
        categories: List[str] | None,
        user_id: str | None = None,
    ) -> str | None:
        """Query the retrieval learner for a matching historical pattern. Issue #2095.

        Issue #3240: user_id scopes the lookup to per-user patterns first, then
        falls back to global patterns when no user-specific match is found.

        Returns the pattern_hash of the best match (for later outcome recording)
        or None when no high-confidence pattern exists.  Strategy hints are
        logged at DEBUG level; callers may inspect them via get_retrieval_learner().

        Args:
            query:      Raw query string.
            complexity: QueryComplexity.value string.
            categories: Optional category list from the search context.
            user_id:    Authenticated user identifier for per-user scope.

        Returns:
            pattern_hash string or None.
        """
        try:
            learner = get_retrieval_learner()
            pattern = await learner.get_matching_pattern(
                query=query,
                complexity=complexity,
                categories=categories,
                user_id=user_id,
            )
            if pattern is not None:
                logger.debug(
                    "RetrievalLearner: matched pattern %s hints=%s",
                    pattern.pattern_hash,
                    pattern.strategy_hints,
                )
                return pattern.pattern_hash
        except Exception as exc:
            logger.debug("RetrievalLearner lookup failed (non-fatal): %s", exc)
        return None

    async def _record_retrieval_outcome(
        self,
        pattern_hash: str | None,
        results: List[RankedResult],
        user_id: str | None = None,
    ) -> None:
        """Record search outcome against the matched retrieval pattern. Issue #2095.

        Issue #3240: user_id is forwarded so the correct namespaced Redis key
        is updated by record_pattern_outcome().

        Success is defined as returning at least one result with hybrid_score >= 0.5,
        which mirrors the threshold used by the context-sufficiency evaluator.

        Args:
            pattern_hash: Hash returned by _lookup_retrieval_pattern(), or None.
            results:      Final search results to evaluate.
            user_id:      Authenticated user identifier for per-user scope.
        """
        if pattern_hash is None:
            return
        try:
            success = any(r.hybrid_score >= 0.5 for r in results)
            learner = get_retrieval_learner()
            await learner.record_pattern_outcome(pattern_hash, success, user_id=user_id)
        except Exception as exc:
            logger.debug("RetrievalLearner outcome recording failed (non-fatal): %s", exc)

    def _record_session_signal(
        self,
        session_id: str,
        results: List[RankedResult],
    ) -> None:
        """Feed retrieval success/miss signal into the session-adaptive reranker. Issue #4690.

        Uses hybrid_score >= 0.5 as the success threshold (mirrors context-sufficiency
        evaluator).  Semantic success is indicated by a high semantic_score component;
        keyword success by a high keyword_score component.

        Args:
            session_id: Conversation/session identifier.
            results:    Final search results after all filtering.
        """
        # A result is a semantic hit if its semantic contribution exceeds threshold.
        # A result is a keyword hit if its keyword contribution exceeds threshold.
        _THRESHOLD = 0.5
        semantic_success = any(r.semantic_score >= _THRESHOLD for r in results)
        keyword_success = any(r.keyword_score >= _THRESHOLD for r in results)
        self._session_reranker.record_signal(
            session_id,
            semantic_success=semantic_success,
            keyword_success=keyword_success,
        )

    def end_session(self, session_id: str) -> None:
        """Discard session-scoped adaptive reranking state for this session. Issue #4690.

        Call at conversation/session end to prevent memory leaks and ensure no
        cross-session state bleed.  No-op if session was never created or feature
        flag is disabled.

        Args:
            session_id: Conversation/session identifier to clear.
        """
        self._session_reranker.end_session(session_id)
