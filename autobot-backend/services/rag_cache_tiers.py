# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RAGService cache tiers, partitioned by visibility scope (#16664).

Tier 0 is the semantic query cache, tier 1 the in-process exact-match cache and tier 2 the topic
retrieval cache. Every tier is read and written inside the caller's cache scope
(``services.rag_visibility.cache_scope``), and a hit is post-filtered like any other result, so a
cached fact is served only to a principal who could read it from the knowledge base. Results are
filtered before they are stored, never after.
"""

from typing import List, Tuple

from advanced_rag_optimizer import RAGMetrics, RankedResult
from autobot_shared.logging_manager import get_llm_logger
from knowledge.search_filters import KbPrincipal
from services.context_sufficiency import SufficiencyVerdict, get_context_sufficiency_evaluator
from services.rag_visibility import RESULT_METADATA_KEY, filter_ranked
from services.semantic_query_cache import get_semantic_query_cache
from services.topic_retrieval_cache import CachedChunk, get_topic_retrieval_cache

logger = get_llm_logger("rag_cache_tiers")

_CachedHit = Tuple[List[RankedResult], RAGMetrics]


class RAGCacheTiersMixin:
    """The cache tiers of ``RAGService``; relies on its ``kb_adapter`` and exact-match cache."""

    def _ownership_manager(self):
        """The KB's ownership manager, or ``None`` (which makes a user-scoped filter return nothing)."""
        return getattr(getattr(getattr(self, "kb_adapter", None), "kb", None), "ownership_manager", None)

    async def _visible(self, results: List[RankedResult], principal: KbPrincipal) -> List[RankedResult]:
        """Post-filter *results* for *principal* (#16664)."""
        return await filter_ranked(results, principal, self._ownership_manager())

    async def _check_topic_cache(self, query: str, principal: KbPrincipal, scope: str) -> _CachedHit | None:
        """Check the topic retrieval cache inside *scope* for related chunks. Issue #1376."""
        try:
            from knowledge.facts import _generate_embedding_with_npu_fallback

            embedding = await _generate_embedding_with_npu_fallback(query)
            if embedding is None:
                return None
            topic_cache = await get_topic_retrieval_cache()
            chunks = await topic_cache.lookup(embedding, scope=scope)
            if chunks is None:
                return None
            results = [
                RankedResult(
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
            results = await self._visible(results, principal)
            if not results:
                return None
            metrics = RAGMetrics()
            metrics.total_time = 0.0
            metrics.final_results_count = len(results)
            return results, metrics
        except Exception as exc:
            logger.debug("Topic cache check failed: %s", exc)
            return None

    async def _store_in_topic_cache(self, results: List[RankedResult], scope: str) -> None:
        """Store already-filtered *results* in the topic retrieval cache under *scope*. Issue #1376."""
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
                    chunks.append(CachedChunk(content=r.content, metadata=r.metadata or {}, score=r.hybrid_score))
            if embeddings:
                topic_cache = await get_topic_retrieval_cache()
                await topic_cache.store(embeddings, chunks, scope=scope)
        except Exception as exc:
            logger.debug("Topic cache store failed: %s", exc)

    async def _check_semantic_cache(self, query: str, principal: KbPrincipal, scope: str) -> _CachedHit | None:
        """Check the semantic query cache inside *scope* for a similar past query. Issue #1372."""
        try:
            sem_cache = await get_semantic_query_cache()
            hit = await sem_cache.lookup(query, scope=scope)
            if hit is None:
                return None
            # Reconstruct a single RankedResult; it carries the stored top result's ownership
            # metadata so the visibility filter can judge it (#16664).
            sr = RankedResult(
                content=hit.response_text,
                metadata={
                    **(hit.metadata.get(RESULT_METADATA_KEY) or {}),
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
            if not await self._visible([sr], principal):
                return None
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
        results: List[RankedResult],
        scope: str,
        model: str = "rag",
    ) -> None:
        """Store already-filtered *results* in the semantic cache under *scope*. Issue #1372."""
        if not results:
            return
        try:
            sem_cache = await get_semantic_query_cache()
            metadata = {
                "result_count": len(results),
                "top_score": results[0].hybrid_score,
                RESULT_METADATA_KEY: results[0].metadata or {},  # #16664: lets a hit be post-filtered
            }
            await sem_cache.store(
                query=query,
                response_text=results[0].content,
                model=model,
                metadata=metadata,
                scope=scope,
            )
        except Exception as exc:
            logger.debug("Semantic cache store failed: %s", exc)

    async def _check_cache_tiers(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        categories: List[str] | None,
        principal: KbPrincipal,
        scope: str | None,
    ) -> Tuple[List[RankedResult], RAGMetrics, str] | None:
        """Check all cache tiers before falling through to ChromaDB. Ref: #1376.

        Returns (results, metrics, cache_key) on hit, None on miss. Every tier is skipped when
        *scope* is None (the ACL epoch was unreadable). Each hit is post-filtered (#16664).
        """
        if scope is None:
            return None
        evaluator = get_context_sufficiency_evaluator()

        # Tier 0: Semantic similarity cache (Issue #1372)
        sem_result = await self._check_semantic_cache(query, principal, scope)
        if sem_result is not None:
            context_text = sem_result[0][0].content
            cached_at = sem_result[0][0].metadata.get("cached_at", 0)
            check = await evaluator.evaluate(query, context_text, cached_at)
            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                return sem_result + ("",)
            logger.info("Semantic cache hit rejected: %s", check.reason)

        # Tier 1: Exact-match cache
        cache_key = self._build_cache_key(query, max_results, enable_reranking, categories, scope)
        cached_result = await self._get_from_cache(cache_key)
        visible = await self._visible(cached_result[0], principal) if cached_result else []
        if visible:
            context_text = " ".join(r.content for r in visible[:3])
            check = await evaluator.evaluate(query, context_text)
            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                return (visible, cached_result[1], cache_key)
            logger.info("Cache hit rejected: %s", check.reason)

        # Tier 2: Topic-level retrieval cache (Issue #1376)
        topic_result = await self._check_topic_cache(query, principal, scope)
        if topic_result is not None:
            return topic_result + (cache_key,)

        return None
