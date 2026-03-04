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
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from advanced_rag_optimizer import AdvancedRAGOptimizer, RAGMetrics, SearchResult
from services.context_sufficiency import (
    SufficiencyVerdict,
    get_context_sufficiency_evaluator,
)
from services.knowledge_base_adapter import KnowledgeBaseAdapter
from services.rag_config import RAGConfig, get_rag_config
from services.semantic_query_cache import get_semantic_query_cache
from services.topic_retrieval_cache import CachedChunk, get_topic_retrieval_cache
from type_defs.common import Metadata

from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("rag_service")


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
        config: Optional[RAGConfig] = None,
    ):
        """
        Initialize RAG service.

        Args:
            knowledge_base: KnowledgeBase or KnowledgeBaseV2 instance
            config: Optional RAG configuration (uses defaults if not provided)
        """
        self.kb_adapter = KnowledgeBaseAdapter(knowledge_base)
        self.config = config or get_rag_config()
        self.optimizer: Optional[AdvancedRAGOptimizer] = None
        self._initialized = False
        self._cache: Dict[str, Tuple[List[SearchResult], float]] = {}
        self._cache_lock = asyncio.Lock()  # CRITICAL: Protect concurrent cache access

        logger.info(
            f"RAGService initialized with {self.kb_adapter.implementation_type}"
        )

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
            self.optimizer = AdvancedRAGOptimizer()

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
        categories: Optional[List[str]],
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
        """Execute search with timeout protection (Issue #665: extracted helper)."""
        return await asyncio.wait_for(
            self.optimizer.advanced_search(
                query=query,
                max_results=fetch_limit,
                enable_reranking=enable_reranking and self.config.enable_reranking,
            ),
            timeout=timeout_seconds,
        )

    async def _execute_and_cache_search(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout_seconds: float,
        categories: Optional[List[str]],
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
                        "Category filter %s eliminated all %d results — "
                        "returning unfiltered results instead",
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
            logger.info(
                f"Advanced search completed: {len(results)} results in {metrics.total_time:.3f}s"
            )
            return results, metrics
        except asyncio.TimeoutError:
            logger.error(
                f"Advanced search timed out after {timeout_seconds}s, using fallback"
            )
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results)
            raise
        except Exception as e:
            logger.error("Advanced search failed: %s", e)
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results)
            raise

    async def _check_topic_cache(
        self, query: str
    ) -> Optional[Tuple[List[SearchResult], RAGMetrics]]:
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

    async def _check_semantic_cache(
        self, query: str
    ) -> Optional[Tuple[List[SearchResult], RAGMetrics]]:
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

    async def _check_cache_tiers(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        categories: Optional[List[str]],
    ) -> Optional[Tuple[List[SearchResult], RAGMetrics, str]]:
        """Check all cache tiers before falling through to ChromaDB. Ref: #1376.

        Returns (results, metrics, cache_key) on hit, None on miss.
        The cache_key is always returned for downstream use.
        """
        evaluator = get_context_sufficiency_evaluator()

        # Tier 0: Semantic similarity cache (Issue #1372)
        sem_result = await self._check_semantic_cache(query)
        if sem_result is not None:
            context_text = sem_result[0][0].content if sem_result[0] else ""
            cached_at = (
                sem_result[0][0].metadata.get("cached_at", 0) if sem_result[0] else 0
            )
            check = await evaluator.evaluate(query, context_text, cached_at)
            if check.verdict != SufficiencyVerdict.INSUFFICIENT:
                return sem_result + ("",)
            logger.info("Semantic cache hit rejected: %s", check.reason)

        # Tier 1: Exact-match cache
        cache_key = self._build_cache_key(
            query, max_results, enable_reranking, categories
        )
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

    async def advanced_search(
        self,
        query: str,
        max_results: int = 5,
        enable_reranking: bool = True,
        timeout: Optional[float] = None,
        categories: Optional[List[str]] = None,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """Perform advanced RAG search with reranking.

        Issue #556: categories. Issue #1372: semantic cache.
        Issue #1376: topic cache. Issue #1374: sufficiency guard.
        """
        if not self.config.enable_advanced_rag:
            return await self._fallback_basic_search(query, max_results, categories)

        hit = await self._check_cache_tiers(
            query, max_results, enable_reranking, categories
        )
        if hit is not None:
            return hit[0], hit[1]

        if not await self.initialize():
            logger.warning("RAG init failed, using fallback")
            return await self._fallback_basic_search(query, max_results, categories)

        cache_key = self._build_cache_key(
            query, max_results, enable_reranking, categories
        )
        timeout_seconds = timeout or self.config.timeout_seconds
        results, metrics = await self._execute_and_cache_search(
            query,
            max_results,
            enable_reranking,
            timeout_seconds,
            categories,
            cache_key,
        )

        # Store in semantic + topic caches for future lookups
        await self._store_in_semantic_cache(query, results)
        await self._store_in_topic_cache(results)

        return results, metrics

    async def get_optimized_context(
        self,
        query: str,
        max_context_length: Optional[int] = None,
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
                f"Requested context length {context_length} exceeds maximum {self.config.max_context_length}"
            ),
            context_length = self.config.max_context_length

        try:
            context, metrics = await self.optimizer.get_optimized_context(
                query=query, max_context_length=context_length
            )

            return context, metrics

        except Exception as e:
            logger.error("Failed to get optimized context: %s", e)
            return f"Error: {str(e)}", RAGMetrics()

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
            reranked = await self.optimizer._rerank_with_cross_encoder(
                query, search_results
            )

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
        categories: Optional[List[str]] = None,
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

            metrics.total_time = time.time() - start_time
            metrics.final_results_count = len(search_results)

            return search_results, metrics

        except Exception as e:
            logger.error("Basic search fallback failed: %s", e)
            return [], metrics

    async def _get_from_cache(
        self, cache_key: str
    ) -> Optional[Tuple[List[SearchResult], RAGMetrics]]:
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

    async def _add_to_cache(
        self, cache_key: str, results: Tuple[List[SearchResult], RAGMetrics]
    ):
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

    async def clear_cache(self):
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


# Global service instance (lazily initialized per knowledge base)
_rag_service_instance: Optional[RAGService] = None
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
