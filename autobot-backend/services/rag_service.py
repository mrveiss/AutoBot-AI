#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RAG Service - Reusable service layer for Advanced RAG capabilities.

Provides clean, dependency-injectable interface for API endpoints.
Handles initialization, caching, error handling, and graceful degradation.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from advanced_rag_optimizer import AdvancedRAGOptimizer, RAGMetrics, SearchResult
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_30_DAYS
from events.bus import publish_event
from events.event_types import RAG_RETRIEVAL
from knowledge.search_components.query_classifier import get_query_classifier
from knowledge.search_components.retrieval_learner import GLOBAL_USER, get_retrieval_learner
from services.context_sufficiency import (
    SufficiencyVerdict,
    get_context_sufficiency_evaluator,
)
from services.knowledge_base_adapter import KnowledgeBaseAdapter
from services.neural_mesh_retriever import NeuralMeshRetriever
from services.rag_config import RAGConfig, get_rag_config
from services.semantic_query_cache import get_semantic_query_cache
from services.session_adaptive_reranker import get_session_adaptive_reranker
from services.topic_retrieval_cache import CachedChunk, get_topic_retrieval_cache
from type_defs.common import Metadata

logger = get_llm_logger("rag_service")

_STREAM_TTL_SECONDS = TTL_30_DAYS

# In-process cache for the DocIndexer hash cache file (Issue #4723).
# The file is only rewritten when indexing completes (infrequent), so reading
# it on every advanced_search() call is unnecessary I/O.
_hash_cache_memo: dict = {}
_hash_cache_loaded_at: float = 0.0
_HASH_CACHE_TTL: float = 60.0  # seconds

# Module-level singleton cache for synthesis schema — avoids repeated disk reads on the
# hot path (_get_kb_synthesis_context is called on every advanced_search). (#4654)
_SYNTHESIS_SCHEMA_CACHE: "object | None" = None


def _get_synthesis_schema() -> "object":
    """Return the cached SynthesisSchema, loading from disk only on first call."""
    global _SYNTHESIS_SCHEMA_CACHE
    if _SYNTHESIS_SCHEMA_CACHE is None:
        from services.knowledge.synthesis_schema_loader import load_synthesis_schema

        _SYNTHESIS_SCHEMA_CACHE = load_synthesis_schema()
    return _SYNTHESIS_SCHEMA_CACHE


class RAGService:
    """
    Reusable RAG service providing advanced knowledge retrieval capabilities.

    Features:
    - Lazy initialization with singleton pattern
    - Graceful degradation to basic search on errors
    - Timeout protection
    - Result caching with TTL
    - FastAPI dependency injection ready
    """

    def __init__(
        self,
        knowledge_base: Any,
        config: RAGConfig | None = None,
    ) -> None:
        """
        Initialize RAG service.

        Args:
            knowledge_base: KnowledgeBase or KnowledgeBaseV2 instance
            config: Optional RAG configuration (uses defaults if not provided)
        """
        self.kb_adapter = KnowledgeBaseAdapter(knowledge_base)
        self.config = config or get_rag_config()
        self.optimizer: AdvancedRAGOptimizer | None = None
        self._initialized = False
        self._cache: Dict[str, Tuple[List[SearchResult], float]] = {}
        self._cache_lock = asyncio.Lock()  # CRITICAL: Protect concurrent cache access
        # Neural Mesh RAG retriever (Issue #2059); injected at startup when Phase 3 is active.
        self._mesh_retriever: Any | None = None
        # Issue #4690: Session-adaptive reranking weight adjuster.
        self._session_reranker = get_session_adaptive_reranker(
            default_semantic=self.config.hybrid_weight_semantic,
            default_keyword=self.config.hybrid_weight_keyword,
        )
        logger.info(f"RAGService initialized with {self.kb_adapter.implementation_type}")

    async def initialize(self) -> bool:
        """
        Initialize the RAG optimizer (lazy initialization).

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized and self.optimizer:
            return True

        try:
            logger.info("Initializing AdvancedRAGOptimizer...")

            # Create optimizer instance
            # Issue #2034: Pass rerank_weights at construction time so
            # RAGConfig.rerank_weights is honoured instead of defaulting to 0.8/0.2.
            self.optimizer = AdvancedRAGOptimizer(rerank_weights=self.config.rerank_weights)

            # Configure from settings
            self.optimizer.hybrid_weight_semantic = self.config.hybrid_weight_semantic
            self.optimizer.hybrid_weight_keyword = self.config.hybrid_weight_keyword
            self.optimizer.max_results_per_stage = self.config.max_results_per_stage
            self.optimizer.diversity_threshold = self.config.diversity_threshold

            # Initialize optimizer with knowledge base
            await self.optimizer.initialize()

            # Inject our knowledge base adapter
            self.optimizer.kb = self.kb_adapter.kb

            self._initialized = True

            # Build a per-instance NeuralMeshRetriever from shared components if not already
            # set (#4765).  Each instance gets its OWN retriever so the search closures bind
            # to THIS instance's optimizer — not to the GraphRAGService optimizer singleton.
            if self._mesh_retriever is None and _shared_mesh_components is not None:
                try:
                    from advanced_rag_optimizer import RAGMetrics as _RAGMetrics

                    _opt = self.optimizer

                    async def _chroma(q: str, k: int) -> list:
                        return await _opt._perform_semantic_search(q, limit=k)

                    async def _hybrid(q: str, top_k: int = 5) -> list:
                        results = await _opt._retrieve_hybrid_results(q, _RAGMetrics())
                        return results[:top_k]

                    self._mesh_retriever = NeuralMeshRetriever(
                        chroma_search=_chroma,
                        hybrid_search=_hybrid,
                        **_shared_mesh_components,
                    )
                    self.config.mesh_retriever_enabled = True
                    logger.debug("Built per-instance NeuralMeshRetriever from shared components (#4765)")
                except Exception as _mesh_err:
                    logger.warning(
                        "Per-instance NeuralMeshRetriever build failed (non-fatal): %s",
                        _mesh_err,
                    )

            logger.info("AdvancedRAGOptimizer initialized successfully")
            return True

        except Exception as e:
            logger.error("Failed to initialize RAG optimizer: %s", e)
            self._initialized = False
            return False

    def _build_cache_key(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        categories: List[str] | None,
    ) -> str:
        """Build cache key for search (Issue #665: extracted helper)."""
        categories_key = ",".join(sorted(categories)) if categories else "all"
        return f"{query}:{max_results}:{enable_reranking}:{categories_key}"

    async def _execute_search_with_timeout(
        self,
        query: str,
        fetch_limit: int,
        enable_reranking: bool,
        timeout_seconds: float,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """Execute search with timeout protection (Issue #665: extracted helper).

        Issue #4696: when enable_rlm_refinement is True, delegates to
        advanced_search_with_refinement() for RLM-driven query refinement.
        The extra refinement_history is logged at debug level and discarded.
        """
        reranking = enable_reranking and self.config.enable_reranking
        if self.config.enable_rlm_refinement:
            results, metrics, history = await asyncio.wait_for(
                self.optimizer.advanced_search_with_refinement(
                    query=query,
                    max_results=fetch_limit,
                    enable_reranking=reranking,
                ),
                timeout=timeout_seconds,
            )
            if history:
                logger.debug(
                    "RLM refinement completed: %d iteration(s) for query %r",
                    len(history),
                    query,
                )
            return results, metrics
        return await asyncio.wait_for(
            self.optimizer.advanced_search(
                query=query,
                max_results=fetch_limit,
                enable_reranking=reranking,
            ),
            timeout=timeout_seconds,
        )

    async def _execute_and_cache_search(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout_seconds: float,
        categories: List[str] | None,
        cache_key: str,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """Helper for advanced_search. Ref: #1088.

        Executes timed search, applies category filter, caches result, and
        handles timeout/exception fallback according to config.
        """
        fetch_limit = max_results * (2 if categories else 1)
        try:
            results, metrics = await self._execute_search_with_timeout(
                query, fetch_limit, enable_reranking, timeout_seconds
            )
            if categories:
                unfiltered_count = len(results)
                filtered = self._filter_by_categories(results, categories)[:max_results]
                if not filtered and unfiltered_count > 0:
                    logger.warning(
                        "Category filter %s eliminated all %d results — " "returning unfiltered results instead",
                        categories,
                        unfiltered_count,
                    )
                else:
                    results = filtered
                    logger.info(
                        "Category filter applied: %s, results: %d/%d",
                        categories,
                        len(results),
                        unfiltered_count,
                    )
                metrics.final_results_count = len(results)
            await self._add_to_cache(cache_key, (results, metrics))
            logger.info(f"Advanced search completed: {len(results)} results in {metrics.total_time:.3f}s")
            return results, metrics
        except asyncio.TimeoutError:
            logger.error(f"Advanced search timed out after {timeout_seconds}s, using fallback")
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results)
            raise
        except Exception as e:
            logger.error("Advanced search failed: %s", e)
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results)
            raise

    async def _check_topic_cache(self, query: str) -> Tuple[List[SearchResult], RAGMetrics] | None:
        """Check topic retrieval cache for related chunks. Issue #1376."""
        try:
            from knowledge.facts import _generate_embedding_with_npu_fallback

            embedding = await _generate_embedding_with_npu_fallback(query)
            if embedding is None:
                return None
            topic_cache = await get_topic_retrieval_cache()
            chunks = await topic_cache.lookup(embedding)
            if chunks is None:
                return None
            results = [
                SearchResult(
                    content=c.content,
                    metadata={**c.metadata, "source": "topic_cache"},
                    semantic_score=c.score,
                    keyword_score=0.0,
                    hybrid_score=c.score,
                    relevance_rank=i + 1,
                    source_path=c.metadata.get("source_path", "topic_cache"),
                )
                for i, c in enumerate(chunks)
            ]
            metrics = RAGMetrics()
            metrics.total_time = 0.0
            metrics.final_results_count = len(results)
            return results, metrics
        except Exception as exc:
            logger.debug("Topic cache check failed: %s", exc)
            return None

    async def _store_in_topic_cache(self, results: List[SearchResult]) -> None:
        """Store search results in topic retrieval cache. Issue #1376."""
        if not results:
            return
        try:
            from knowledge.facts import _generate_embedding_with_npu_fallback

            embeddings = []
            chunks = []
            for r in results[:10]:
                emb = await _generate_embedding_with_npu_fallback(r.content)
                if emb is not None:
                    embeddings.append(emb)
                    chunks.append(
                        CachedChunk(
                            content=r.content,
                            metadata=r.metadata or {},
                            score=r.hybrid_score,
                        )
                    )
            if embeddings:
                topic_cache = await get_topic_retrieval_cache()
                await topic_cache.store(embeddings, chunks)
        except Exception as exc:
            logger.debug("Topic cache store failed: %s", exc)

    async def _check_semantic_cache(self, query: str) -> Tuple[List[SearchResult], RAGMetrics] | None:
        """Check semantic query cache for similar past queries. Issue #1372."""
        try:
            sem_cache = await get_semantic_query_cache()
            hit = await sem_cache.lookup(query)
            if hit is None:
                return None
            # Reconstruct a single SearchResult from cached response
            sr = SearchResult(
                content=hit.response_text,
                metadata={
                    "source": "semantic_cache",
                    "model": hit.model,
                    "original_query": hit.original_query,
                    "similarity_score": hit.similarity_score,
                },
                semantic_score=hit.similarity_score,
                keyword_score=0.0,
                hybrid_score=hit.similarity_score,
                relevance_rank=1,
                source_path="semantic_cache",
            )
            metrics = RAGMetrics()
            metrics.total_time = 0.0
            metrics.final_results_count = 1
            return [sr], metrics
        except Exception as exc:
            logger.debug("Semantic cache check failed: %s", exc)
            return None

    async def _store_in_semantic_cache(
        self,
        query: str,
        results: List[SearchResult],
        model: str = "rag",
    ) -> None:
        """Store search results in semantic cache. Issue #1372."""
        if not results:
            return
        try:
            sem_cache = await get_semantic_query_cache()
            # Cache the top result's content as the response
            top_content = results[0].content if results else ""
            metadata = {
                "result_count": len(results),
                "top_score": results[0].hybrid_score if results else 0,
            }
            await sem_cache.store(
                query=query,
                response_text=top_content,
                model=model,
                metadata=metadata,
            )
        except Exception as exc:
            logger.debug("Semantic cache store failed: %s", exc)

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
        results: List[SearchResult],
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
        results: List[SearchResult],
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

    async def _emit_retrieval_feedback(
        self,
        query: str,
        retrieved_ids: List[str],
        ranked_ids: List[str],
        complexity: str = "simple",
    ) -> None:
        """Publish a rag_retrieval live event after each search. Issue #1516.

        Fires publish_live_event("global", RAG_RETRIEVAL, ...) so that
        Neural Mesh RAG (#1994) consumers can observe retrieval patterns in
        real time via the /ws/live WebSocket endpoint.

        Args:
            query: Raw query string.
            retrieved_ids: Chunk IDs retrieved before reranking.
            ranked_ids: Final ordered chunk IDs after reranking.
            complexity: QueryComplexity.value string (Issue #2024).
        """
        payload = {
            "query_text": query,
            "retrieved_chunk_ids": retrieved_ids,
            "final_ranked_ids": ranked_ids,
            "complexity": complexity,
            "timestamp": time.time(),
        }
        try:
            await publish_event("global", RAG_RETRIEVAL, payload)
        except Exception as exc:
            logger.debug("Live event publish failed (non-fatal): %s", exc)

    async def _store_feedback_in_stream(
        self,
        query: str,
        retrieved_ids: List[str],
        ranked_ids: List[str],
        complexity: str = "simple",
        user_id: str | None = None,
    ) -> None:
        """Append retrieval feedback to a dated, user-scoped Redis stream. Issue #1516.

        Issue #3240: Stream key changed from ``rag:feedback:{date}`` to
        ``rag:feedback:{user_id}:{date}`` so each user's feedback drives their
        own personalised retrieval patterns.  When user_id is None the global
        sentinel ``__global__`` is used, preserving backward compatibility.

        TTL: 30 days so Neural Mesh Phase 3 (#2056) can consume the data
        before it expires. Increased from 7 days — Fix: #2102.

        Args:
            query:         Raw query string.
            retrieved_ids: Chunk IDs retrieved before reranking.
            ranked_ids:    Final ordered chunk IDs after reranking.
            complexity:    QueryComplexity.value string (Issue #2024).
            user_id:       Authenticated user identifier; defaults to global scope.
        """
        uid = user_id or GLOBAL_USER
        date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        stream_key = f"rag:feedback:{uid}:{date_key}"
        entry = {
            "query_text": query,
            "retrieved_chunk_ids": json.dumps(retrieved_ids, ensure_ascii=False),
            "final_ranked_ids": json.dumps(ranked_ids, ensure_ascii=False),
            "complexity": complexity,
            "timestamp": str(time.time()),
        }
        try:
            redis = await get_async_redis_client(database="analytics")
            if redis is None:
                logger.debug("Redis unavailable; skipping feedback stream write")
                return
            await redis.xadd(stream_key, entry)
            await redis.expire(stream_key, _STREAM_TTL_SECONDS)
            logger.debug("Wrote retrieval feedback to %s", stream_key)
        except Exception as exc:
            logger.debug("Feedback stream write failed (non-fatal): %s", exc)

    async def _check_cache_tiers(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        categories: List[str] | None,
    ) -> Tuple[List[SearchResult], RAGMetrics, str] | None:
        """Check all cache tiers before falling through to ChromaDB. Ref: #1376.

        Returns (results, metrics, cache_key) on hit, None on miss.
        The cache_key is always returned for downstream use.
        """
        evaluator = get_context_sufficiency_evaluator()

        # Tier 0: Semantic similarity cache (Issue #1372)
        sem_result = await self._check_semantic_cache(query)
        if sem_result is not None:
            context_text = sem_result[0][0].content if sem_result[0] else ""
            cached_at = sem_result[0][0].metadata.get("cached_at", 0) if sem_result[0] else 0
            check = await evaluator.evaluate(query, context_text, cached_at)
            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                return sem_result + ("",)
            logger.info("Semantic cache hit rejected: %s", check.reason)

        # Tier 1: Exact-match cache
        cache_key = self._build_cache_key(query, max_results, enable_reranking, categories)
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            context_text = " ".join(r.content for r in cached_result[0][:3])
            check = await evaluator.evaluate(query, context_text)
            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                return cached_result + (cache_key,)
            logger.info("Cache hit rejected: %s", check.reason)

        # Tier 2: Topic-level retrieval cache (Issue #1376)
        topic_result = await self._check_topic_cache(query)
        if topic_result is not None:
            return topic_result + (cache_key,)

        return None

    async def _run_mesh_retriever(
        self,
        query: str,
        max_results: int,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """Delegate retrieval to NeuralMeshRetriever and emit feedback. Issue #2059.

        Called only when mesh_retriever_enabled=True and _mesh_retriever is set.
        The mesh retriever returns SearchResult-compatible chunks directly; this
        helper handles feedback emission so the caller stays clean.
        """
        logger.info("Using NeuralMeshRetriever for query (mesh_retriever_enabled=True)")
        mesh_result = await self._mesh_retriever.retrieve(query, max_results)
        results: List[SearchResult] = mesh_result.chunks
        metrics = RAGMetrics()
        metrics.final_results_count = len(results)

        retrieved_ids = [r.metadata.get("chunk_id", r.source_path) for r in results]
        await self._emit_retrieval_feedback(
            query=query,
            retrieved_ids=retrieved_ids,
            ranked_ids=retrieved_ids,
        )
        await self._store_feedback_in_stream(
            query=query,
            retrieved_ids=retrieved_ids,
            ranked_ids=retrieved_ids,
        )
        return results, metrics

    async def _emit_ranked_feedback(
        self,
        query: str,
        results: List[SearchResult],
        user_id: str | None = None,
    ) -> None:
        """Classify query complexity and emit retrieval feedback to event + Redis stream.

        Issue #3240: user_id is forwarded to _store_feedback_in_stream so the
        feedback lands in the correct per-user Redis stream.

        ranked_ids: results already sorted by rerank_score (post-rerank order).
        retrieved_ids: re-sorted by hybrid_score to recover pre-rerank retrieval order.
        Ref: #2024, #1516, #2035, #2735.
        """
        classifier = get_query_classifier()
        complexity = classifier.classify(query)
        ranked_ids = [r.metadata.get("chunk_id", r.source_path) for r in results]
        pre_rerank_order = sorted(results, key=lambda r: r.hybrid_score, reverse=True)
        retrieved_ids = [r.metadata.get("chunk_id", r.source_path) for r in pre_rerank_order]
        await self._emit_retrieval_feedback(
            query=query,
            retrieved_ids=retrieved_ids,
            ranked_ids=ranked_ids,
            complexity=complexity.value,
        )
        await self._store_feedback_in_stream(
            query=query,
            retrieved_ids=retrieved_ids,
            ranked_ids=ranked_ids,
            complexity=complexity.value,
            user_id=user_id,
        )

    async def advanced_search(
        self,
        query: str,
        max_results: int = 5,
        enable_reranking: bool = True,
        timeout: float | None = None,
        categories: List[str] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """Perform advanced RAG search with reranking.

        Issue #556: categories. Issue #1372: semantic cache.
        Issue #1376: topic cache. Issue #1374: sufficiency guard.
        Issue #3240: user_id scopes retrieval pattern lookup and feedback
        storage to the authenticated user, enabling personalised RAG behaviour.
        Issue #4690: session_id enables session-adaptive reranking weight
        adjustment when ``enable_session_adaptive_reranking`` is True.

        Args:
            query:            Search query string.
            max_results:      Maximum number of results to return.
            enable_reranking: Whether to apply cross-encoder reranking.
            timeout:          Override timeout in seconds.
            categories:       Optional category filter list.
            user_id:          Authenticated user identifier; None uses global scope.
            session_id:       Conversation session identifier for adaptive reranking.
        """
        if not self.config.enable_advanced_rag:
            return await self._fallback_basic_search(query, max_results, categories)

        hit = await self._check_cache_tiers(query, max_results, enable_reranking, categories)
        if hit is not None:
            return hit[0], hit[1]

        # Neural Mesh RAG path (Issue #2059)
        if self.config.mesh_retriever_enabled and self._mesh_retriever is not None:
            return await self._run_mesh_retriever(query, max_results)

        if not await self.initialize():
            logger.warning("RAG init failed, using fallback")
            return await self._fallback_basic_search(query, max_results, categories)

        # Issue #4690: Apply session-adapted weights before executing the search so
        # the optimizer uses weights refined by earlier hits/misses in this session.
        _prev_semantic: float | None = None
        _prev_keyword: float | None = None
        if self.config.enable_session_adaptive_reranking and session_id and self.optimizer:
            _prev_semantic = self.optimizer.hybrid_weight_semantic
            _prev_keyword = self.optimizer.hybrid_weight_keyword
            adapted_sem, adapted_kw = self._session_reranker.get_weights(session_id)
            self.optimizer.hybrid_weight_semantic = adapted_sem
            self.optimizer.hybrid_weight_keyword = adapted_kw
            logger.debug(
                "Session adaptive reranking [%s]: sem=%.3f kw=%.3f",
                session_id,
                adapted_sem,
                adapted_kw,
            )

        # Issue #2095/#3240: consult retrieval learner with user_id for personalised hints.
        classifier = get_query_classifier()
        complexity = classifier.classify(query)
        pattern_hash = await self._lookup_retrieval_pattern(
            query=query,
            complexity=complexity.value,
            categories=categories,
            user_id=user_id,
        )

        cache_key = self._build_cache_key(query, max_results, enable_reranking, categories)
        timeout_seconds = timeout or self.config.timeout_seconds
        results, metrics = await self._execute_and_cache_search(
            query,
            max_results,
            enable_reranking,
            timeout_seconds,
            categories,
            cache_key,
        )

        # Issue #4690: Restore original weights so other non-session callers are unaffected.
        if _prev_semantic is not None and self.optimizer:
            self.optimizer.hybrid_weight_semantic = _prev_semantic
            self.optimizer.hybrid_weight_keyword = _prev_keyword  # type: ignore[assignment]

        # Issue #4953: merge autobot_docs results when category is requested or
        # no category filter is active (search-all).
        if categories is None or "autobot_docs" in categories:
            try:
                from services.knowledge.doc_indexer import get_doc_indexer_service

                doc_svc = get_doc_indexer_service()
                if doc_svc._initialized:
                    doc_results = await doc_svc.search(query, n_results=max_results)
                    if doc_results:
                        combined = results + doc_results
                        combined.sort(key=lambda r: r.hybrid_score, reverse=True)
                        results = combined[:max_results]
                        logger.debug("autobot_docs merged %d result(s) into search", len(doc_results))
            except Exception as _doc_exc:
                logger.debug("autobot_docs search skipped: %s", _doc_exc)

        # Issue #4689: filter chunks whose source_path is absent from the hash cache
        # (file was removed/moved since last index run).
        results = await self._filter_stale_chunks(results)

        # Store in semantic + topic caches for future lookups
        await self._store_in_semantic_cache(query, results)
        await self._store_in_topic_cache(results)

        # Issue #3240: emit user-scoped feedback to personalised Redis stream.
        await self._emit_ranked_feedback(query, results, user_id=user_id)

        # Issue #2095/#3240: record outcome so the learner can update success_rate.
        await self._record_retrieval_outcome(pattern_hash, results, user_id=user_id)

        # Issue #4690: Record session-scoped retrieval signal for future weight adaptation.
        if self.config.enable_session_adaptive_reranking and session_id:
            self._record_session_signal(session_id, results)

        return results, metrics

    async def get_optimized_context(
        self,
        query: str,
        max_context_length: int | None = None,
    ) -> Tuple[str, RAGMetrics]:
        """
        Get optimized context for RAG-based response generation.

        Args:
            query: Search query string
            max_context_length: Maximum context length (uses config default if not provided)

        Returns:
            Tuple of (optimized_context, metrics)
        """
        if not await self.initialize():
            return "RAG optimizer not available", RAGMetrics()

        context_length = max_context_length or self.config.default_context_length

        # Enforce maximum context length
        if context_length > self.config.max_context_length:
            logger.warning(
                "Requested context length %d exceeds maximum %d",
                context_length,
                self.config.max_context_length,
            )
            context_length = self.config.max_context_length

        try:
            context, metrics = await self.optimizer.get_optimized_context(
                query=query, max_context_length=context_length
            )

            # Issue #4564: enrich context with KB synthesis summaries (optional)
            synthesis_prefix = await self._get_kb_synthesis_context(query)
            if synthesis_prefix:
                context = synthesis_prefix + "\n\n" + context

            # Issue #4678: optionally inject AnalyzerService lessons (low-weight)
            if self.config.enable_analyzer_lessons:
                lessons_ctx = await self._get_analyzer_lessons_context(query)
                if lessons_ctx:
                    context = context + "\n\n" + lessons_ctx

            return context, metrics

        except Exception as e:
            logger.error("Failed to get optimized context: %s", e)
            return "Error: RAG context retrieval failed", RAGMetrics()

    async def _get_kb_synthesis_context(self, query: str) -> str:
        """Query all KB synthesis ChromaDB collections for enrichment (Issue #4564, #4635).

        Queries the default ``kb_synthesis`` collection plus any
        ``synthesis_target`` collections defined in synthesis_schema.yaml.
        Results from all collections are merged.  Per-collection errors are
        logged and swallowed so the main context path is never interrupted.
        """
        from knowledge.backends import get_async_default_client

        # Collect all synthesis collection names: default + schema-defined targets.
        collection_names: List[str] = ["kb_synthesis"]
        try:
            schema = _get_synthesis_schema()
            for col in schema.collections:
                target = col.synthesis_target.strip()
                if target and target not in collection_names:
                    collection_names.append(target)
        except Exception as exc:
            logger.debug("Could not load synthesis schema (non-fatal): %s", exc)

        all_docs: List[str] = []
        try:
            client = await get_async_default_client()
        except Exception as exc:
            logger.debug("KB synthesis ChromaDB client unavailable (non-fatal): %s", exc)
            return ""

        for col_name in collection_names:
            try:
                collection = await client.get_or_create_collection(name=col_name)
                results = await collection.query(query_texts=[query], n_results=2)
                if results and results.get("ids") and results["ids"][0]:
                    docs = results.get("documents", [[]])[0]
                    all_docs.extend(d for d in docs if d)
            except Exception as exc:
                logger.debug("KB synthesis fetch from '%s' failed (non-fatal): %s", col_name, exc)

        if not all_docs:
            return ""
        return "KB synthesis summaries:\n" + "\n".join(f"- {d}" for d in all_docs)

    async def _get_analyzer_lessons_context(self, query: str) -> str:
        """Query the ``autobot_lessons`` ChromaDB collection for supplemental context.

        Issue #4678: Injects AnalyzerService-distilled lessons as low-weight
        supplemental context after primary synthesis summaries.  Requires
        ``RAGConfig.enable_analyzer_lessons`` to be True (checked by caller).

        Returns an empty string on any error so the main context path is never
        interrupted.
        """
        try:
            from knowledge.backends import get_async_default_client

            client = await get_async_default_client()
            collection = await client.get_or_create_collection(name="autobot_lessons")
            results = await collection.query(query_texts=[query], n_results=2)
            if not (results and results.get("ids") and results["ids"][0]):
                return ""
            docs = results.get("documents", [[]])[0]
            relevant = [d for d in docs if d]
            if not relevant:
                return ""
            return "Analyzer lessons:\n" + "\n".join(f"- {d}" for d in relevant)
        except Exception as exc:
            logger.debug("Analyzer lessons fetch failed (non-fatal): %s", exc)
            return ""

    async def rerank_results(
        self,
        query: str,
        results: List[Metadata],
    ) -> List[Metadata]:
        """
        Rerank existing search results using cross-encoder.

        This is useful for post-processing results from basic searches.

        Args:
            query: Original search query
            results: List of search results to rerank

        Returns:
            Reranked list of results with rerank_score added
        """
        if not await self.initialize():
            logger.warning("RAG optimizer not available, returning original results")
            return results

        try:
            # Convert results to SearchResult objects
            search_results = []
            for i, result in enumerate(results):
                sr = SearchResult(
                    content=result.get("content", result.get("text", "")),
                    metadata=result.get("metadata", {}),
                    semantic_score=result.get("score", 0.0),
                    keyword_score=0.0,
                    hybrid_score=result.get("score", 0.0),
                    relevance_rank=i + 1,
                    source_path=result.get("metadata", {}).get("source", "unknown"),
                )
                search_results.append(sr)

            # Apply reranking
            reranked = await self.optimizer._rerank_with_cross_encoder(query, search_results)

            # Convert back to dictionaries
            reranked_dicts = []
            for result in reranked:
                result_dict = results[result.relevance_rank - 1].copy()
                result_dict["rerank_score"] = result.rerank_score
                result_dict["original_rank"] = result.relevance_rank
                reranked_dicts.append(result_dict)

            logger.info("Reranked %s results", len(reranked_dicts))
            return reranked_dicts

        except Exception as e:
            logger.error("Reranking failed: %s", e)
            return results

    async def _filter_stale_chunks(
        self,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """Filter out chunks whose source_path is absent from the DocIndexer hash cache.

        Issue #4689: chunks for files removed/moved since the last index run must
        not reach the LLM context.  If the hash cache is unavailable (file missing,
        parse error) the method returns the original list unchanged so RAG is never
        disrupted by a cache I/O failure.

        The check is path-presence only (not hash equality); we trust that the
        DocIndexer re-indexes changed files on the next cycle.

        Returns:
            Filtered list (stale chunks dropped) or original list on cache failure.
        """
        import json as _json
        from pathlib import Path as _Path

        try:
            from services.knowledge.doc_indexer import HASH_CACHE_FILE

            cache_path: _Path = HASH_CACHE_FILE
        except Exception as exc:
            logger.debug("Could not import HASH_CACHE_FILE (skipping provenance check): %s", exc)
            return results

        def _load() -> dict:
            if not cache_path.exists():
                return {}
            try:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    return _json.load(fh)
            except Exception:
                return {}

        try:
            global _hash_cache_memo, _hash_cache_loaded_at
            now = time.monotonic()
            if now - _hash_cache_loaded_at > _HASH_CACHE_TTL:
                _hash_cache_memo = await asyncio.to_thread(_load)
                _hash_cache_loaded_at = now
            hash_cache: dict = _hash_cache_memo
        except Exception as exc:
            logger.debug("Hash cache load failed (skipping provenance check): %s", exc)
            return results

        if not hash_cache:
            # Empty cache means indexer hasn't run yet; skip filtering to avoid
            # dropping all results on a fresh deployment.
            return results

        valid: List[SearchResult] = []
        stale_paths: List[str] = []
        for chunk in results:
            if chunk.source_path in hash_cache:
                valid.append(chunk)
            else:
                stale_paths.append(chunk.source_path)

        if stale_paths:
            logger.warning(
                "Provenance check: dropped %d stale chunk(s) — source paths absent from " "hash cache: %s",
                len(stale_paths),
                stale_paths[:10],  # cap log line length
            )

        return valid

    def _filter_by_categories(
        self,
        results: List[SearchResult],
        categories: List[str],
    ) -> List[SearchResult]:
        """
        Filter search results by category.

        Issue #556: Category-based filtering for chat RAG.

        Args:
            results: List of search results to filter
            categories: List of category names to include

        Returns:
            Filtered list of results matching any of the specified categories
        """
        if not categories:
            return results

        categories_set: Set[str] = set(categories)
        filtered = []

        for result in results:
            # Check category in metadata
            result_category = result.metadata.get("category", "")

            # Also check category_id or category_path
            if not result_category:
                result_category = result.metadata.get("category_id", "")
            if not result_category:
                result_category = result.metadata.get("category_path", "")

            # Match against categories (exact match or path prefix)
            if result_category:
                # Handle hierarchical categories (e.g., "system_knowledge/commands")
                category_parts = result_category.split("/")
                if any(part in categories_set for part in category_parts):
                    filtered.append(result)
                elif result_category in categories_set:
                    filtered.append(result)
            else:
                # If no category metadata, include by default (uncategorized)
                # This can be changed to exclude if strict category filtering is needed
                filtered.append(result)

        if not filtered and results:
            actual_categories = {r.metadata.get("category", "<none>") for r in results}
            logger.debug(
                "Category filter: 0/%d matched %s — actual categories: %s",
                len(results),
                categories,
                actual_categories,
            )
        else:
            logger.debug(
                "Category filter: %d/%d results matched categories %s",
                len(filtered),
                len(results),
                categories,
            )
        return filtered

    async def _fallback_basic_search(
        self,
        query: str,
        max_results: int,
        categories: List[str] | None = None,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """
        Fallback to basic search when advanced RAG fails.

        Issue #556: Added categories parameter for filtering.

        Args:
            query: Search query
            max_results: Maximum results to return
            categories: Optional list of categories to filter

        Returns:
            Tuple of (basic_results, empty_metrics)
        """
        logger.info("Using basic search fallback")
        metrics = RAGMetrics()

        try:
            start_time = time.time()

            # Fetch more if filtering by category
            fetch_limit = max_results * 2 if categories else max_results

            # Use knowledge base adapter for consistent interface
            basic_results = await self.kb_adapter.search(query=query, top_k=fetch_limit)

            # Convert to SearchResult objects
            search_results = []
            for i, result in enumerate(basic_results):
                sr = SearchResult(
                    content=result.get("content", result.get("text", "")),
                    metadata=result.get("metadata", {}),
                    semantic_score=result.get("score", 0.0),
                    keyword_score=0.0,
                    hybrid_score=result.get("score", 0.0),
                    relevance_rank=i + 1,
                    source_path=result.get("metadata", {}).get("source", "unknown"),
                )
                search_results.append(sr)

            # Apply category filter if specified
            if categories:
                search_results = self._filter_by_categories(search_results, categories)
                search_results = search_results[:max_results]

            # Issue #4721: filter stale chunks on the fallback path too.
            search_results = await self._filter_stale_chunks(search_results)

            metrics.total_time = time.time() - start_time
            metrics.final_results_count = len(search_results)

            return search_results, metrics

        except Exception as e:
            logger.error("Basic search fallback failed: %s", e)
            return [], metrics

    async def _get_from_cache(self, cache_key: str) -> Tuple[List[SearchResult], RAGMetrics] | None:
        """Get results from cache if not expired."""
        # CRITICAL: Protect cache access with lock to prevent race conditions
        async with self._cache_lock:
            if cache_key in self._cache:
                cached_results, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self.config.cache_ttl_seconds:
                    return cached_results, RAGMetrics()  # Return cached results
                else:
                    # Remove expired entry
                    del self._cache[cache_key]
        return None

    async def _add_to_cache(self, cache_key: str, results: Tuple[List[SearchResult], RAGMetrics]) -> None:
        """Add results to cache with timestamp.

        Args:
            cache_key: Cache key string
            results: Tuple of (search_results_list, metrics)
        """
        # CRITICAL: Protect cache modifications with lock to prevent race conditions
        # Store only the search results list, not the full tuple
        search_results, _ = results
        async with self._cache_lock:
            self._cache[cache_key] = (search_results, time.time())

            # Simple cache size management (LRU-like)
            if len(self._cache) > 100:
                # Remove oldest entries
                sorted_cache = sorted(self._cache.items(), key=lambda x: x[1][1])
                for key, _ in sorted_cache[:20]:  # Remove oldest 20%
                    del self._cache[key]

    async def clear_cache(self) -> None:
        """Clear the result cache."""
        async with self._cache_lock:
            self._cache.clear()
        logger.info("RAG service cache cleared")

    def get_stats(self) -> Metadata:
        """Get service statistics."""
        return {
            "initialized": self._initialized,
            "kb_implementation": self.kb_adapter.implementation_type,
            "cache_entries": len(self._cache),
            "config": self.config.to_dict(),
        }


# Shared mesh components — registered by lifespan at startup (#4765).
# Each RAGService.initialize() builds its OWN NeuralMeshRetriever from these components so
# the search closures are bound to THAT instance's optimizer, not to a shared singleton.
_shared_mesh_components: Dict[str, Any] | None = None


def register_shared_mesh_components(components: Dict[str, Any]) -> None:
    """Register mesh brain components for per-instance NeuralMeshRetriever construction.

    Called once by lifespan._init_graph_rag_service().  Every subsequent
    RAGService.initialize() builds its own retriever with closures bound to its
    own optimizer (#4765).

    Args:
        components: dict with keys mesh_db, ppr, edge_learner, reranker, classifier.
    """
    global _shared_mesh_components
    _shared_mesh_components = components
    logger.info("Mesh brain components registered for per-instance retriever (#4765)")


def get_shared_mesh_components() -> Dict[str, Any] | None:
    """Return the registered mesh components, or None if not yet registered."""
    return _shared_mesh_components


# ---------------------------------------------------------------------------
# Legacy singleton kept for backward compatibility — no longer used by
# RAGService.initialize() (replaced by per-instance build from components above).
# Retained so external callers importing this symbol don't break.
# ---------------------------------------------------------------------------
_shared_mesh_retriever: Any | None = None


def register_shared_mesh_retriever(retriever: Any) -> None:
    """Deprecated: register a pre-built retriever singleton.

    Kept for backward compatibility.  Prefer register_shared_mesh_components()
    so each RAGService gets its own retriever bound to its own optimizer (#4765).
    """
    global _shared_mesh_retriever
    _shared_mesh_retriever = retriever
    logger.info("NeuralMeshRetriever registered as shared singleton (legacy #4757)")


# Global service instance (lazily initialized per knowledge base)
_rag_service_instance: RAGService | None = None
_rag_service_lock = asyncio.Lock()


async def get_rag_service(knowledge_base: Any) -> RAGService:
    """
    Get or create RAG service instance (thread-safe).

    This function is designed for FastAPI dependency injection.

    Args:
        knowledge_base: KnowledgeBase instance

    Returns:
        RAGService instance
    """
    global _rag_service_instance

    if _rag_service_instance is None:
        async with _rag_service_lock:
            # Double-check after acquiring lock
            if _rag_service_instance is None:
                _rag_service_instance = RAGService(knowledge_base)
                await _rag_service_instance.initialize()

    return _rag_service_instance
