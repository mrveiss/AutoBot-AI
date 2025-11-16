#!/usr/bin/env python3
"""
RAG Service - Reusable service layer for Advanced RAG capabilities.

Provides clean, dependency-injectable interface for API endpoints.
Handles initialization, caching, error handling, and graceful degradation.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.services.knowledge_base_adapter import KnowledgeBaseAdapter
from backend.services.rag_config import RAGConfig, get_rag_config
from src.advanced_rag_optimizer import (
    AdvancedRAGOptimizer,
    RAGMetrics,
    SearchResult,
)
from src.utils.logging_manager import get_llm_logger

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
            logger.error(f"Failed to initialize RAG optimizer: {e}")
            self._initialized = False
            return False

    async def advanced_search(
        self,
        query: str,
        max_results: int = 5,
        enable_reranking: bool = True,
        timeout: Optional[float] = None,
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """
        Perform advanced RAG search with reranking.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            enable_reranking: Whether to apply cross-encoder reranking
            timeout: Optional timeout in seconds (uses config default if not provided)

        Returns:
            Tuple of (search_results, metrics)
        """
        if not self.config.enable_advanced_rag:
            logger.info("Advanced RAG disabled in configuration")
            return await self._fallback_basic_search(query, max_results)

        # Check cache first
        cache_key = f"{query}:{max_results}:{enable_reranking}"
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for query: '{query[:50]}...'")
            return cached_result

        # Ensure initialized
        if not await self.initialize():
            logger.warning("RAG optimizer initialization failed, using fallback")
            return await self._fallback_basic_search(query, max_results)

        # Apply timeout
        timeout_seconds = timeout or self.config.timeout_seconds

        try:
            # Run advanced search with timeout protection
            results, metrics = await asyncio.wait_for(
                self.optimizer.advanced_search(
                    query=query,
                    max_results=max_results,
                    enable_reranking=enable_reranking and self.config.enable_reranking,
                ),
                timeout=timeout_seconds,
            )

            # Cache successful results
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
            logger.error(f"Advanced search failed: {e}")
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results)
            raise

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
            )
            context_length = self.config.max_context_length

        try:
            context, metrics = await self.optimizer.get_optimized_context(
                query=query, max_context_length=context_length
            )

            return context, metrics

        except Exception as e:
            logger.error(f"Failed to get optimized context: {e}")
            return f"Error: {str(e)}", RAGMetrics()

    async def rerank_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
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

            logger.info(f"Reranked {len(reranked_dicts)} results")
            return reranked_dicts

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results

    async def _fallback_basic_search(
        self, query: str, max_results: int
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """
        Fallback to basic search when advanced RAG fails.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            Tuple of (basic_results, empty_metrics)
        """
        logger.info("Using basic search fallback")
        metrics = RAGMetrics()

        try:
            start_time = time.time()

            # Use knowledge base adapter for consistent interface
            basic_results = await self.kb_adapter.search(
                query=query, top_k=max_results
            )

            metrics.total_time = time.time() - start_time
            metrics.final_results_count = len(basic_results)

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

            return search_results, metrics

        except Exception as e:
            logger.error(f"Basic search fallback failed: {e}")
            return [], metrics

    async def _get_from_cache(
        self, cache_key: str
    ) -> Optional[Tuple[List[SearchResult], RAGMetrics]]:
        """Get results from cache if not expired."""
        # CRITICAL: Protect cache access with lock to prevent race conditions
        async with self._cache_lock:
            if cache_key in self._cache:
                results, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self.config.cache_ttl_seconds:
                    return results, RAGMetrics()  # Return cached results
                else:
                    # Remove expired entry
                    del self._cache[cache_key]
        return None

    async def _add_to_cache(
        self, cache_key: str, results: Tuple[List[SearchResult], RAGMetrics]
    ):
        """Add results to cache with timestamp."""
        # CRITICAL: Protect cache modifications with lock to prevent race conditions
        async with self._cache_lock:
            self._cache[cache_key] = (results, time.time())

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

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "initialized": self._initialized,
            "kb_implementation": self.kb_adapter.implementation_type,
            "cache_entries": len(self._cache),
            "config": self.config.to_dict(),
        }


# Global service instance (lazily initialized per knowledge base)
_rag_service_instance: Optional[RAGService] = None


async def get_rag_service(knowledge_base: Any) -> RAGService:
    """
    Get or create RAG service instance.

    This function is designed for FastAPI dependency injection.

    Args:
        knowledge_base: KnowledgeBase instance

    Returns:
        RAGService instance
    """
    global _rag_service_instance

    if _rag_service_instance is None:
        _rag_service_instance = RAGService(knowledge_base)
        await _rag_service_instance.initialize()

    return _rag_service_instance
