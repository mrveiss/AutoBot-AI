#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Advanced RAG Optimization System
Implements sophisticated retrieval strategies for enhanced knowledge access

Features:
- Hybrid search combining vector similarity and keyword matching
- Multi-level relevance scoring with semantic reranking
- Dynamic context window optimization based on query complexity
- GPU-accelerated embedding computation with RTX 4070 optimization
- Query expansion and reformulation for improved recall
- Result diversification to avoid redundant information
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_llm_logger
from backend.constants.model_constants import model_config
from backend.utils.semantic_chunker_gpu import get_gpu_semantic_chunker

logger = get_llm_logger("advanced_rag_optimizer")

# Performance optimization: O(1) lookup for troubleshooting keywords (Issue #326)
TROUBLESHOOTING_KEYWORDS = {"error", "problem", "issue", "trouble"}


@dataclass
class SearchResult:
    """Enhanced search result with multiple relevance scores."""

    content: str
    metadata: Dict[str, Any]
    semantic_score: float
    keyword_score: float
    hybrid_score: float
    relevance_rank: int
    source_path: str
    chunk_index: int = 0
    rerank_score: Optional[float] = None


@dataclass
class QueryContext:
    """Context information for optimizing retrieval strategy."""

    original_query: str
    expanded_queries: List[str] = field(default_factory=list)
    query_type: str = "general"  # general, technical, procedural, troubleshooting
    complexity_score: float = 0.5
    optimal_context_length: int = 2000
    suggested_chunk_count: int = 5


@dataclass
class RAGMetrics:
    """Performance metrics for RAG operations."""

    query_processing_time: float = 0.0
    retrieval_time: float = 0.0
    reranking_time: float = 0.0
    total_time: float = 0.0
    documents_considered: int = 0
    final_results_count: int = 0
    gpu_acceleration_used: bool = False
    hybrid_search_enabled: bool = False


class AdvancedRAGOptimizer:
    """
    Advanced RAG optimizer implementing state-of-the-art retrieval strategies.

    Key improvements:
    1. Hybrid search (semantic + keyword) for comprehensive recall
    2. Multi-stage reranking with cross-encoder models
    3. Dynamic context optimization based on query analysis
    4. Query expansion for improved coverage
    5. Result diversification to reduce redundancy
    6. GPU acceleration for embedding operations
    """

    def __init__(self):
        """Initialize RAG optimizer with search configuration. Issue #620."""
        self.kb = None
        self.semantic_chunker = None
        self._init_search_config()
        self._init_query_patterns()
        self._init_performance_tracking()
        logger.info("AdvancedRAGOptimizer initialized")

    def _init_search_config(self) -> None:
        """Initialize search configuration parameters. Issue #620."""
        self.hybrid_weight_semantic = 0.7  # Weight for semantic similarity
        self.hybrid_weight_keyword = 0.3  # Weight for keyword matching
        self.max_results_per_stage = 20  # Results to consider in each stage
        self.diversity_threshold = 0.85  # Similarity threshold for diversification

    def _init_query_patterns(self) -> None:
        """Initialize query analysis keyword patterns. Issue #620."""
        self.technical_keywords = self._get_technical_keywords()
        self.procedural_keywords = self._get_procedural_keywords()

    def _get_technical_keywords(self) -> set:
        """Return set of technical keywords for query classification. Issue #620."""
        return {
            "install",
            "configure",
            "setup",
            "deploy",
            "build",
            "compile",
            "debug",
            "error",
            "troubleshoot",
            "fix",
            "repair",
            "resolve",
            "api",
            "endpoint",
            "function",
            "method",
            "class",
            "module",
            "docker",
            "container",
            "service",
            "server",
            "client",
        }

    def _get_procedural_keywords(self) -> set:
        """Return set of procedural keywords for query classification. Issue #620."""
        return {
            "how to",
            "step by",
            "tutorial",
            "guide",
            "instructions",
            "procedure",
            "process",
            "workflow",
            "setup",
            "getting started",
        }

    def _init_performance_tracking(self) -> None:
        """Initialize performance tracking components. Issue #620."""
        self.query_cache = {}
        self.cache_ttl_seconds = 300  # 5 minutes

    async def initialize(self):
        """Initialize knowledge base and components."""
        try:
            # Use singleton factory to get properly initialized knowledge base
            # This ensures consistent KB state across the application
            from knowledge import get_knowledge_base

            self.kb = await get_knowledge_base()

            # Initialize semantic chunker for query processing
            self.semantic_chunker = get_gpu_semantic_chunker()

            logger.info("Advanced RAG optimizer initialized successfully")
            return True

        except Exception as e:
            logger.error("Failed to initialize RAG optimizer: %s", e)
            return False

    def _analyze_query_context(self, query: str) -> QueryContext:
        """Analyze query to determine optimal retrieval strategy."""
        query_lower = query.lower()

        # Determine query type
        query_type = "general"
        complexity_score = 0.5

        if any(kw in query_lower for kw in self.technical_keywords):
            query_type = "technical"
            complexity_score = 0.8
        elif any(kw in query_lower for kw in self.procedural_keywords):
            query_type = "procedural"
            complexity_score = 0.6
        elif any(word in query_lower for word in TROUBLESHOOTING_KEYWORDS):
            query_type = "troubleshooting"
            complexity_score = 0.9

        # Generate expanded queries
        expanded_queries = self._expand_query(query, query_type)

        # Determine optimal context length based on complexity
        # Uses centralized constants from model_constants.py for maintainability
        if complexity_score > 0.8:
            optimal_context_length = model_config.RAG_CONTEXT_HIGH_COMPLEXITY
            suggested_chunk_count = model_config.RAG_CHUNKS_HIGH_COMPLEXITY
        elif complexity_score > 0.6:
            optimal_context_length = model_config.RAG_CONTEXT_MEDIUM_COMPLEXITY
            suggested_chunk_count = model_config.RAG_CHUNKS_MEDIUM_COMPLEXITY
        else:
            optimal_context_length = model_config.RAG_CONTEXT_LOW_COMPLEXITY
            suggested_chunk_count = model_config.RAG_CHUNKS_LOW_COMPLEXITY

        context = QueryContext(
            original_query=query,
            expanded_queries=expanded_queries,
            query_type=query_type,
            complexity_score=complexity_score,
            optimal_context_length=optimal_context_length,
            suggested_chunk_count=suggested_chunk_count,
        )

        logger.debug(
            f"Query analysis: type={query_type}, complexity={complexity_score:.2f}"
        )
        return context

    def _expand_query(self, query: str, query_type: str) -> List[str]:
        """Generate expanded queries for improved recall."""
        expanded = [query]  # Always include original

        # Add synonyms and related terms based on query type
        if query_type == "technical":
            # Add common technical synonyms
            if "install" in query.lower():
                expanded.append(query.replace("install", "setup"))
                expanded.append(query.replace("install", "deploy"))
            if "configure" in query.lower():
                expanded.append(query.replace("configure", "setup"))
                expanded.append(query.replace("configure", "config"))

        elif query_type == "troubleshooting":
            # Add problem-solving variations
            if "error" in query.lower():
                expanded.append(query.replace("error", "issue"))
                expanded.append(query.replace("error", "problem"))
            expanded.append(f"how to fix {query}")
            expanded.append(f"troubleshoot {query}")

        # Add general variations
        expanded.append(f"autobot {query}")  # Context-specific

        # Remove duplicates and limit
        unique_expanded = list(dict.fromkeys(expanded))[:5]

        logger.debug("Query expansion: %s variants generated", len(unique_expanded))
        return unique_expanded

    async def _perform_semantic_search(
        self, query: str, limit: int = 20
    ) -> List[SearchResult]:
        """Perform semantic similarity search using embeddings."""
        try:
            # Use knowledge base's search method for semantic search
            # Issue #429: Fixed - was incorrectly calling get_fact(query=query)
            # get_fact() only accepts fact_id, not query. Use search() instead.
            facts = await self.kb.search(query, top_k=limit)

            semantic_results = []
            for i, fact in enumerate(facts[:limit]):
                # Extract metadata - already a dict from search results
                # Issue #429: Fixed - metadata is already parsed, no need for json.loads
                metadata = fact.get("metadata", {})

                # Create search result with semantic scoring
                result = SearchResult(
                    content=fact.get("content", ""),
                    metadata=metadata,
                    semantic_score=0.8 - (i * 0.05),  # Decrease score by rank
                    keyword_score=0.0,  # Will be computed later
                    hybrid_score=0.0,  # Will be computed later
                    relevance_rank=i + 1,
                    source_path=metadata.get("relative_path", "unknown"),
                    chunk_index=metadata.get("chunk_index", 0),
                )
                semantic_results.append(result)

            logger.debug("Semantic search returned %s results", len(semantic_results))
            return semantic_results

        except Exception as e:
            logger.error("Semantic search failed: %s", e)
            return []

    def _calculate_keyword_score(
        self, query_lower: str, query_terms: set, combined_text: str
    ) -> float:
        """Calculate keyword score for a fact. Issue #620."""
        matches = sum(1 for term in query_terms if term in combined_text)
        if matches == 0:
            return 0.0
        keyword_score = matches / len(query_terms)
        # Boost score for exact phrase matches
        if query_lower in combined_text:
            keyword_score *= 1.5
        return keyword_score

    def _create_keyword_result(self, fact: Dict, keyword_score: float) -> SearchResult:
        """Create SearchResult from fact with keyword score. Issue #620."""
        metadata = fact.get("metadata", {})
        return SearchResult(
            content=fact.get("content", ""),
            metadata=metadata,
            semantic_score=0.0,
            keyword_score=keyword_score,
            hybrid_score=0.0,
            relevance_rank=0,
            source_path=metadata.get("relative_path", "unknown"),
            chunk_index=metadata.get("chunk_index", 0),
        )

    def _perform_keyword_search(
        self, query: str, all_facts: List[Dict]
    ) -> List[SearchResult]:
        """Perform keyword-based search with TF-IDF-like scoring. Issue #620."""
        try:
            query_lower = query.lower()
            query_terms = set(query_lower.split())
            keyword_results = []

            for fact in all_facts:
                content = fact.get("content", "").lower()
                metadata_str = json.dumps(fact.get("metadata", {})).lower()
                combined_text = f"{content} {metadata_str}"

                score = self._calculate_keyword_score(
                    query_lower, query_terms, combined_text
                )
                if score > 0:
                    keyword_results.append(self._create_keyword_result(fact, score))

            keyword_results.sort(key=lambda x: x.keyword_score, reverse=True)
            for i, result in enumerate(keyword_results):
                result.relevance_rank = i + 1

            logger.debug("Keyword search returned %s results", len(keyword_results))
            return keyword_results[:20]

        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []

    def _combine_hybrid_results(
        self, semantic_results: List[SearchResult], keyword_results: List[SearchResult]
    ) -> List[SearchResult]:
        """Combine semantic and keyword results with hybrid scoring."""

        # Create a mapping by content to combine scores
        result_map = {}

        # Add semantic results
        for result in semantic_results:
            key = hash(result.content[:100])  # Use first 100 chars as key
            result_map[key] = result

        # Merge keyword results
        for result in keyword_results:
            key = hash(result.content[:100])

            if key in result_map:
                # Combine scores
                existing = result_map[key]
                existing.keyword_score = max(
                    existing.keyword_score, result.keyword_score
                )
            else:
                # New result from keyword search
                result_map[key] = result

        # Calculate hybrid scores
        combined_results = []
        for result in result_map.values():
            result.hybrid_score = (
                self.hybrid_weight_semantic * result.semantic_score
                + self.hybrid_weight_keyword * result.keyword_score
            )
            combined_results.append(result)

        # Sort by hybrid score
        combined_results.sort(key=lambda x: x.hybrid_score, reverse=True)

        # Update final ranks
        for i, result in enumerate(combined_results):
            result.relevance_rank = i + 1

        logger.debug("Hybrid combination produced %s results", len(combined_results))
        return combined_results

    def _diversify_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove redundant results to improve diversity."""
        if len(results) <= 1:
            return results

        diversified = [results[0]]  # Always include top result

        for candidate in results[1:]:
            # Check similarity with already selected results
            is_diverse = True
            # Cache candidate.content.lower() outside inner loop (Issue #323)
            candidate_words = set(candidate.content.lower().split())

            for selected in diversified:
                # Simple diversity check based on content similarity
                selected_words = set(selected.content.lower().split())

                if candidate_words and selected_words:
                    intersection = len(candidate_words & selected_words)
                    union = len(candidate_words | selected_words)
                    similarity = intersection / union if union > 0 else 0

                    if similarity > self.diversity_threshold:
                        is_diverse = False
                        break

            if is_diverse:
                diversified.append(candidate)

                # Limit diversified results
                if len(diversified) >= 10:
                    break

        logger.debug("Diversification: %s → %s results", len(results), len(diversified))
        return diversified

    def _ensure_cross_encoder_loaded(self) -> None:
        """Lazy load cross-encoder model (Issue #398: extracted)."""
        if hasattr(self, "_cross_encoder"):
            return

        try:
            from sentence_transformers import CrossEncoder

            model_name = getattr(
                self, "reranking_model", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            )
            logger.info("Loading cross-encoder model: %s", model_name)
            self._cross_encoder = CrossEncoder(model_name)
            logger.info("Cross-encoder model loaded successfully")
        except ImportError:
            logger.warning(
                "sentence-transformers not available, using fallback reranking"
            )
            self._cross_encoder = None
        except Exception as e:
            logger.error("Failed to load cross-encoder model: %s", e)
            self._cross_encoder = None

    async def _apply_cross_encoder_scores(
        self, query: str, results: List[SearchResult]
    ) -> None:
        """Apply cross-encoder scores to results (Issue #398: extracted)."""
        pairs = [(query, result.content) for result in results]
        cross_encoder_scores = await asyncio.to_thread(
            self._cross_encoder.predict, pairs
        )

        for result, ce_score in zip(results, cross_encoder_scores):
            result.rerank_score = float(ce_score) * 0.8 + result.hybrid_score * 0.2

        logger.debug("Cross-encoder reranking completed for %s results", len(results))

    def _apply_fallback_reranking(
        self, query: str, results: List[SearchResult]
    ) -> None:
        """Apply term-based fallback reranking (Issue #398: extracted)."""
        logger.debug("Using fallback term-based reranking")
        query_lower = query.lower()
        query_terms = query_lower.split()

        for result in results:
            content_lower = result.content.lower()
            term_matches = sum(1 for term in query_terms if term in content_lower)
            exact_match_bonus = 2 if query_lower in content_lower else 0
            result.rerank_score = (
                result.hybrid_score * 0.7
                + (term_matches / len(query_terms)) * 0.2
                + exact_match_bonus * 0.1
            )

    def _finalize_rerank_results(
        self, results: List[SearchResult]
    ) -> List[SearchResult]:
        """Sort and rank results after reranking (Issue #398: extracted)."""
        results.sort(key=lambda x: x.rerank_score or 0, reverse=True)
        for i, result in enumerate(results):
            result.relevance_rank = i + 1
        logger.debug("Reranking completed: top score = %.3f", results[0].rerank_score)
        return results

    async def _rerank_with_cross_encoder(
        self, query: str, results: List[SearchResult]
    ) -> List[SearchResult]:
        """Rerank results using cross-encoder model (Issue #398: refactored)."""
        try:
            self._ensure_cross_encoder_loaded()

            if self._cross_encoder is not None:
                await self._apply_cross_encoder_scores(query, results)
            else:
                self._apply_fallback_reranking(query, results)

            return self._finalize_rerank_results(results)

        except Exception as e:
            logger.error("Reranking failed: %s", e)
            return results

    async def advanced_search(
        self, query: str, max_results: int = 5, enable_reranking: bool = True
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """
        Perform advanced RAG search with all optimizations (Issue #665: refactored).

        Returns:
            (search_results, performance_metrics)
        """
        start_time = time.time()
        metrics = RAGMetrics()

        try:
            logger.info("Advanced search: '%s' (max_results=%s)", query, max_results)

            # Step 1: Query analysis and context optimization
            query_start = time.time()
            context = self._analyze_query_context(query)
            metrics.query_processing_time = time.time() - query_start

            # Step 2: Multi-strategy retrieval
            hybrid_results = await self._retrieve_hybrid_results(query, metrics)

            # Step 3: Result diversification and reranking
            final_results = await self._diversify_and_rerank(
                query, hybrid_results, enable_reranking, metrics
            )

            # Step 4: Apply context optimization and limit results
            optimized_results = self._optimize_result_count(
                final_results, max_results, context
            )

            metrics.final_results_count = len(optimized_results)
            metrics.total_time = time.time() - start_time
            metrics.gpu_acceleration_used = True  # Semantic chunker uses GPU

            self._log_search_completion(metrics, context)

            return optimized_results, metrics

        except Exception as e:
            logger.error("Advanced search failed: %s", e)
            metrics.total_time = time.time() - start_time
            return [], metrics

    async def _retrieve_hybrid_results(
        self, query: str, metrics: RAGMetrics
    ) -> List[SearchResult]:
        """Perform hybrid retrieval (Issue #665: extracted helper)."""
        retrieval_start = time.time()

        # Issue #619: Parallelize semantic search and facts retrieval
        semantic_results, all_facts = await asyncio.gather(
            self._perform_semantic_search(query, limit=self.max_results_per_stage),
            self.kb.get_all_facts(),
        )

        # Keyword search (needs all_facts from above)
        keyword_results = self._perform_keyword_search(query, all_facts)

        # Combine with hybrid scoring
        hybrid_results = self._combine_hybrid_results(semantic_results, keyword_results)

        metrics.retrieval_time = time.time() - retrieval_start
        metrics.documents_considered = len(hybrid_results)
        metrics.hybrid_search_enabled = True

        return hybrid_results

    async def _diversify_and_rerank(
        self,
        query: str,
        results: List[SearchResult],
        enable_reranking: bool,
        metrics: RAGMetrics,
    ) -> List[SearchResult]:
        """Diversify and optionally rerank results (Issue #665: extracted helper)."""
        diversified_results = self._diversify_results(results)

        if enable_reranking and len(diversified_results) > 1:
            rerank_start = time.time()
            final_results = await self._rerank_with_cross_encoder(
                query, diversified_results
            )
            metrics.reranking_time = time.time() - rerank_start
            return final_results

        return diversified_results

    def _optimize_result_count(
        self,
        results: List[SearchResult],
        max_results: int,
        context: Any,
    ) -> List[SearchResult]:
        """Optimize result count based on context (Issue #665: extracted helper)."""
        optimized_results = results[:max_results]

        # Adjust chunk count based on query context
        if (
            len(optimized_results) < context.suggested_chunk_count
            and len(results) > max_results
        ):
            optimized_results = results[: context.suggested_chunk_count]

        return optimized_results

    def _log_search_completion(self, metrics: RAGMetrics, context: Any) -> None:
        """Log search completion metrics (Issue #665: extracted helper)."""
        logger.info("Advanced search completed:")
        logger.info("  - Total time: %.3fs", metrics.total_time)
        logger.info("  - Documents considered: %s", metrics.documents_considered)
        logger.info("  - Final results: %s", metrics.final_results_count)
        logger.info("  - Query type: %s", context.query_type)

    def _build_context_parts(
        self,
        results: List[SearchResult],
        max_context_length: int,
        query_context: QueryContext,
    ) -> List[str]:
        """Build context parts from search results with length optimization.

        Args:
            results: Search results to build context from.
            max_context_length: Maximum total context length.
            query_context: Query context for complexity-based decisions.

        Returns:
            List of formatted context entries.

        Issue #620.
        """
        context_parts = []
        current_length = 0

        for i, result in enumerate(results):
            source_info = f"Source: {result.source_path}"
            if result.chunk_index > 0:
                source_info += f" (section {result.chunk_index + 1})"

            context_entry = f"{source_info}\nContent: {result.content}\n"
            entry_length = len(context_entry)

            if current_length + entry_length > max_context_length and context_parts:
                break

            context_parts.append(context_entry)
            current_length += entry_length

            if i >= 2 and query_context.complexity_score < 0.6:
                break

        return context_parts

    def _build_context_header(
        self, query: str, context_parts: List[str], query_context: QueryContext
    ) -> str:
        """Build the header for optimized context output.

        Args:
            query: Original query string.
            context_parts: List of context entries.
            query_context: Query context with type information.

        Returns:
            Formatted header string.

        Issue #620.
        """
        header = f"Relevant Information for: {query}\n"
        header += f"Sources: {len(context_parts)} documents\n"
        header += f"Query type: {query_context.query_type}\n\n"
        return header

    async def get_optimized_context(
        self, query: str, max_context_length: int = 2000
    ) -> Tuple[str, RAGMetrics]:
        """Get optimized context for RAG-based response generation."""
        try:
            results, metrics = await self.advanced_search(query, max_results=8)

            if not results:
                return "No relevant information found.", metrics

            query_context = self._analyze_query_context(query)
            context_parts = self._build_context_parts(
                results, max_context_length, query_context
            )
            header = self._build_context_header(query, context_parts, query_context)
            final_context = header + "\n---\n".join(context_parts)

            logger.info(
                "Optimized context generated: %s characters from %s sources",
                len(final_context),
                len(context_parts),
            )

            return final_context, metrics

        except Exception as e:
            logger.error("Context optimization failed: %s", e)
            return f"Error retrieving context: {str(e)}", RAGMetrics()

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for the RAG optimizer."""
        return {
            "hybrid_search_enabled": True,
            "semantic_weight": self.hybrid_weight_semantic,
            "keyword_weight": self.hybrid_weight_keyword,
            "diversity_threshold": self.diversity_threshold,
            "max_results_per_stage": self.max_results_per_stage,
            "cache_enabled": bool(self.query_cache),
            "gpu_acceleration": self.semantic_chunker is not None,
        }


# Global instance for system integration (thread-safe)
import asyncio as _asyncio_lock

_rag_optimizer_instance = None
_rag_optimizer_lock = _asyncio_lock.Lock()


async def get_rag_optimizer() -> AdvancedRAGOptimizer:
    """Get the global RAG optimizer instance (thread-safe)."""
    global _rag_optimizer_instance

    if _rag_optimizer_instance is None:
        async with _rag_optimizer_lock:
            # Double-check after acquiring lock
            if _rag_optimizer_instance is None:
                _rag_optimizer_instance = AdvancedRAGOptimizer()
                await _rag_optimizer_instance.initialize()

    return _rag_optimizer_instance


# Convenience functions for integration
async def advanced_knowledge_search(
    query: str, max_results: int = 5
) -> List[SearchResult]:
    """Perform advanced knowledge search with all optimizations."""
    optimizer = await get_rag_optimizer()
    results, _ = await optimizer.advanced_search(query, max_results)
    return results


async def get_optimized_knowledge_context(query: str, max_length: int = 2000) -> str:
    """Get optimized knowledge context for response generation."""
    optimizer = await get_rag_optimizer()
    context, _ = await optimizer.get_optimized_context(query, max_length)
    return context


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Advanced RAG Optimizer Test")
    parser.add_argument("query", help="Search query to test")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum results")
    parser.add_argument("--context", action="store_true", help="Get optimized context")

    args = parser.parse_args()

    async def main():
        """Run CLI query against optimized RAG search."""
        if args.context:
            context = await get_optimized_knowledge_context(args.query)
            print("=== Optimized Context ===")
            print(context)
        else:
            results = await advanced_knowledge_search(args.query, args.max_results)
            print(f"=== Search Results for: {args.query} ===")
            for i, result in enumerate(results, 1):
                print(f"\nResult {i}:")
                print(f"  Source: {result.source_path}")
                print(f"  Hybrid Score: {result.hybrid_score:.3f}")
                print(f"  Content: {result.content[:200]}...")

    asyncio.run(main())
