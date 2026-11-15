#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from typing import Any, Dict, List, Tuple

from advanced_rag_optimizer import AdvancedRAGOptimizer, RAGMetrics, RankedResult
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_30_DAYS
from events.bus import publish_event
from events.event_types import RAG_RETRIEVAL
from knowledge.chunk_identity import resolve_chunk_id
from knowledge.search_components.query_classifier import get_query_classifier
from knowledge.search_components.retrieval_learner import GLOBAL_USER
from knowledge.search_filters import KbPrincipal, require_kb_principal
from services.knowledge_base_adapter import KnowledgeBaseAdapter
from services.neural_mesh_retriever import NeuralMeshRetriever
from services.rag_cache_tiers import RAGCacheTiersMixin
from services.rag_config import RAGConfig, get_rag_config
from services.rag_derived_context import RAGDerivedContextMixin
from services.rag_learning import RAGLearningMixin
from services.rag_legs import RAGLegsMixin
from services.rag_visibility import VISIBILITY_OVERFETCH, cache_scope, filter_ranked
from services.retrieval_contract import DEFAULT_PLAN, RetrievalPlan, finalize_hits, require_plan
from services.session_adaptive_reranker import get_session_adaptive_reranker, session_adapted_weights
from type_defs.common import Metadata

logger = get_llm_logger("rag_service")

_STREAM_TTL_SECONDS = TTL_30_DAYS

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


def reset_synthesis_schema_cache() -> None:
    """Clear the module-level synthesis-schema cache so the next call reloads from disk.

    Primary use is test isolation: the ``is None`` guard in ``_get_synthesis_schema``
    means the first unpatched load permanently caches the real on-disk schema for the
    whole process, silently ignoring later ``load_synthesis_schema`` patches. An autouse
    fixture (see ``conftest.py``) calls this between tests. It is also a manual
    invalidation seam if a caller ever needs to force a reload at runtime. (#12531)
    """
    global _SYNTHESIS_SCHEMA_CACHE
    _SYNTHESIS_SCHEMA_CACHE = None


class RAGService(RAGDerivedContextMixin, RAGCacheTiersMixin, RAGLegsMixin, RAGLearningMixin):
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
        self._cache: Dict[str, Tuple[List[RankedResult], float]] = {}
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
            # Issue #10600: forward BM25-hybrid, relevance-floor, and MMR knobs so
            # the optimizer honours the config-gated retrieval-quality flips.
            self.optimizer = AdvancedRAGOptimizer(
                rerank_weights=self.config.rerank_weights,
                bm25_hybrid_enabled=self.config.bm25_hybrid_enabled,
                min_score=self.config.min_score,
                mmr_lambda=self.config.mmr_lambda,
            )

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
                        config=self.config,
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
        scope: str | None,
    ) -> str:
        """Build cache key for search (Issue #665: extracted helper).

        Prefixed with the visibility *scope* (#16664), so one scope never reads another's entry.
        An empty key (no scope: the ACL epoch was unreadable) means "do not cache".
        """
        if scope is None:
            return ""
        categories_key = ",".join(sorted(categories)) if categories else "all"
        return f"{scope}:{query}:{max_results}:{enable_reranking}:{categories_key}"

    async def _emit_retrieval_feedback(
        self,
        query: str,
        retrieved_ids: List[str],
        ranked_ids: List[str],
        complexity: str = "simple",
    ) -> None:
        """Publish a rag_retrieval live event after each search. Issue #1516.

        Fires publish_event("global", RAG_RETRIEVAL, ...) so that
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

    async def _run_mesh_retriever(
        self,
        query: str,
        max_results: int,
        principal: KbPrincipal,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """Delegate retrieval to NeuralMeshRetriever and emit feedback. Issue #2059.

        Called only when mesh_retriever_enabled=True and _mesh_retriever is set.
        Drops stale chunks like every other branch (#18141) and keeps only what
        *principal* may read (#16664), then emits feedback.
        """
        logger.info("Using NeuralMeshRetriever for query (mesh_retriever_enabled=True)")
        mesh_result = await self._mesh_retriever.retrieve(query, max_results * VISIBILITY_OVERFETCH)
        results = await self._filter_stale_chunks(mesh_result.ranked_chunks())
        results = (await filter_ranked(results, principal, self._ownership_manager()))[:max_results]
        metrics = RAGMetrics()
        metrics.final_results_count = len(results)

        retrieved_ids = [resolve_chunk_id(r) for r in results]
        await self._emit_retrieval_feedback(query=query, retrieved_ids=retrieved_ids, ranked_ids=retrieved_ids)
        await self._store_feedback_in_stream(query=query, retrieved_ids=retrieved_ids, ranked_ids=retrieved_ids)
        return results, metrics

    async def _emit_ranked_feedback(
        self,
        query: str,
        results: List[RankedResult],
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
        ranked_ids = [resolve_chunk_id(r) for r in results]
        pre_rerank_order = sorted(results, key=lambda r: r.hybrid_score, reverse=True)
        retrieved_ids = [resolve_chunk_id(r) for r in pre_rerank_order]
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
        *,
        principal: KbPrincipal,
        plan: RetrievalPlan = DEFAULT_PLAN,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """Perform advanced RAG search with reranking: THE retrieval entry (#20950, #21606).

        Issue #16664: ``principal`` is required. Every leg returns only what it may read and the
        caches are partitioned by its scope; ``SYSTEM_SCOPE`` reads non-private facts only.

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
            principal:        Who is asking (``kb_principal(user)``) or ``SYSTEM_SCOPE``; None raises.
            plan:             Per-technique toggles (#21606); ``DEFAULT_PLAN`` is today's behaviour.
                              Toggles with no leg yet are listed in ``metrics.unsupported``.

        Every hit carries ``get_provenance(hit)``: bucket, leg, per-leg scores and final score.
        """
        principal = require_kb_principal(principal)  # before any read (#16664)
        plan = require_plan(plan)
        results, metrics = await self._search_under_plan(
            query,
            max_results,
            enable_reranking and plan.rerank,
            timeout,
            categories,
            user_id,
            session_id,
            principal,
            plan,
        )
        return finalize_hits(results, metrics, plan)

    async def _search_under_plan(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout: float | None,
        categories: List[str] | None,
        user_id: str | None,
        session_id: str | None,
        principal: KbPrincipal,
        plan: RetrievalPlan,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """The tiered search (cache, mesh, optimizer, docs, stale cut) under *plan*, then its feedback."""
        if not self.config.enable_advanced_rag:
            return await self._fallback_basic_search(query, max_results, categories, principal=principal)

        # The cache toggle off makes the scope None: every tier is skipped, read and write (#20958).
        scope = await cache_scope(principal) if plan.cache else None
        # Tiers 0 and 2 hold results that already include docs, so a docs-less plan never reads them;
        # tier 1 is stored before the docs merge and is shared, so the key needs no plan part.
        hit = await self._check_cache_tiers(
            query, max_results, enable_reranking, categories, principal, scope, shared_tiers=plan.docs
        )
        if hit is not None:
            return hit[0], hit[1]

        # Neural Mesh RAG path (Issue #2059)
        if self.config.mesh_retriever_enabled and self._mesh_retriever is not None:
            return await self._run_mesh_retriever(query, max_results, principal)

        if not await self.initialize():
            logger.warning("RAG init failed, using fallback")
            return await self._fallback_basic_search(query, max_results, categories, principal=principal)

        results, metrics, pattern_hash = await self._optimizer_leg(
            query, max_results, enable_reranking, timeout, categories, user_id, session_id, principal, scope
        )
        results = await self._finish_search(query, results, categories, max_results, principal, scope, plan)
        await self._record_search_feedback(query, results, pattern_hash, user_id, session_id)
        return results, metrics

    async def _optimizer_leg(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout: float | None,
        categories: List[str] | None,
        user_id: str | None,
        session_id: str | None,
        principal: KbPrincipal,
        scope: str | None,
    ) -> Tuple[List[RankedResult], RAGMetrics, str | None]:
        """The optimizer search with session-adapted weights (#4690) and the pattern lookup (#2095)."""
        # Issue #4690: session-adapted weights apply to this search only; the
        # context manager restores them even if the search raises.
        adapting = bool(self.config.enable_session_adaptive_reranking and session_id)
        # The guard this replaced was `enabled and session_id and self.optimizer`,
        # so the reranker is reached only once the optimizer is known to exist --
        # tests build this service with `__new__` and set only what they need.
        adapting_optimizer = self.optimizer if adapting else None
        with session_adapted_weights(
            adapting_optimizer, self._session_reranker if adapting_optimizer else None, session_id, enabled=adapting
        ):
            # Issue #2095/#3240: consult retrieval learner with user_id for personalised hints.
            complexity = get_query_classifier().classify(query)
            pattern_hash = await self._lookup_retrieval_pattern(
                query=query, complexity=complexity.value, categories=categories, user_id=user_id
            )
            cache_key = self._build_cache_key(query, max_results, enable_reranking, categories, scope)
            timeout_seconds = timeout or self.config.timeout_seconds
            results, metrics = await self._execute_and_cache_search(
                query, max_results, enable_reranking, timeout_seconds, categories, cache_key, principal
            )
        return results, metrics, pattern_hash

    async def _finish_search(
        self,
        query: str,
        results: List[RankedResult],
        categories: List[str] | None,
        max_results: int,
        principal: KbPrincipal,
        scope: str | None,
        plan: RetrievalPlan,
    ) -> List[RankedResult]:
        """Docs merge, stale cut, then the semantic and topic cache stores, all inside *scope*."""
        if plan.docs:
            results = await self._merge_docs_leg(query, results, categories, max_results, principal)

        # Issue #4689: drop doc chunks whose file has left the doc index (knowledge.stale_filter).
        results = await self._filter_stale_chunks(results)

        # Store the filtered results in the semantic + topic caches, inside this scope. A docs-less
        # plan never stores: its results would be served to plans that include docs.
        if scope is not None and plan.docs:
            await self._store_in_semantic_cache(query, results, scope)
            await self._store_in_topic_cache(results, scope)
        return results

    async def _record_search_feedback(
        self,
        query: str,
        results: List[RankedResult],
        pattern_hash: str | None,
        user_id: str | None,
        session_id: str | None,
    ) -> None:
        """Feedback stream (#3240), pattern outcome (#2095) and session signal (#4690) for a finished search."""
        await self._emit_ranked_feedback(query, results, user_id=user_id)
        await self._record_retrieval_outcome(pattern_hash, results, user_id=user_id)
        if self.config.enable_session_adaptive_reranking and session_id:
            self._record_session_signal(session_id, results)

    async def get_optimized_context(
        self,
        query: str,
        max_context_length: int | None = None,
        *,
        principal: KbPrincipal,
    ) -> Tuple[str, RAGMetrics]:
        """
        Get optimized context for RAG-based response generation.

        Issue #18944: ``principal`` is required (``kb_principal(user)`` or ``SYSTEM_SCOPE``); the optimizer
        results and the synthesis and lessons legs keep only what it may read. None raises.

        Args:
            query: Search query string
            max_context_length: Maximum context length (uses config default if not provided)
            principal: Who is asking

        Returns:
            Tuple of (optimized_context, metrics)
        """
        principal = require_kb_principal(principal)  # before any read (#18944)
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
                query=query, max_context_length=context_length, principal=principal
            )

            # Issue #4564: enrich context with KB synthesis summaries (optional)
            synthesis_prefix = await self._get_kb_synthesis_context(query, principal)
            if synthesis_prefix:
                context = synthesis_prefix + "\n\n" + context

            # Issue #4678: optionally inject AnalyzerService lessons (low-weight)
            if self.config.enable_analyzer_lessons:
                lessons_ctx = await self._get_analyzer_lessons_context(query, principal)
                if lessons_ctx:
                    context = context + "\n\n" + lessons_ctx

            return context, metrics

        except Exception as e:
            logger.error("Failed to get optimized context: %s", e)
            return "Error: RAG context retrieval failed", RAGMetrics()

    async def _get_kb_synthesis_context(self, query: str, principal: KbPrincipal) -> str:
        """Query all KB synthesis ChromaDB collections for enrichment (Issue #4564, #4635).

        Queries the default ``kb_synthesis`` collection plus any
        ``synthesis_target`` collections defined in synthesis_schema.yaml.
        Results from all collections are merged.  Per-collection errors are
        logged and swallowed so the main context path is never interrupted.
        Issue #18944: each hit is kept only if *principal* may read it (:meth:`_visible_synthesis_docs`).
        """
        principal = require_kb_principal(principal)
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
                all_docs.extend(await self._visible_synthesis_docs(collection, query, principal))
            except Exception as exc:
                logger.debug("KB synthesis fetch from '%s' failed (non-fatal): %s", col_name, exc)

        if not all_docs:
            return ""
        return "KB synthesis summaries:\n" + "\n".join(f"- {d}" for d in all_docs)

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
            # Convert results to RankedResult objects
            search_results = []
            for i, result in enumerate(results):
                sr = RankedResult(
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

    async def _get_from_cache(self, cache_key: str) -> Tuple[List[RankedResult], RAGMetrics] | None:
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

    async def _add_to_cache(self, cache_key: str, results: Tuple[List[RankedResult], RAGMetrics]) -> None:
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
