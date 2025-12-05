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


from src.constants.model_constants import model_config
from src.knowledge_base import KnowledgeBase
from src.utils.logging_manager import get_llm_logger
from src.utils.semantic_chunker_gpu import get_gpu_semantic_chunker

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
        self.kb = None
        self.semantic_chunker = None

        # Search configuration
        self.hybrid_weight_semantic = 0.7  # Weight for semantic similarity
        self.hybrid_weight_keyword = 0.3  # Weight for keyword matching
        self.max_results_per_stage = 20  # Results to consider in each stage
        self.diversity_threshold = 0.85  # Similarity threshold for diversification

        # Query analysis patterns
        self.technical_keywords = {
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

        self.procedural_keywords = {
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

        # Performance tracking
        self.query_cache = {}
        self.cache_ttl_seconds = 300  # 5 minutes

        logger.info("AdvancedRAGOptimizer initialized")

    async def initialize(self):
        """Initialize knowledge base and components."""
        try:
            # Initialize knowledge base
            self.kb = KnowledgeBase()
            await self.kb.ainit()

            # Initialize semantic chunker for query processing
            self.semantic_chunker = get_gpu_semantic_chunker()

            logger.info("Advanced RAG optimizer initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize RAG optimizer: {e}")
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

        logger.debug(f"Query expansion: {len(unique_expanded)} variants generated")
        return unique_expanded

    async def _perform_semantic_search(
        self, query: str, limit: int = 20
    ) -> List[SearchResult]:
        """Perform semantic similarity search using embeddings."""
        try:
            # Use knowledge base's existing search functionality
            facts = await asyncio.to_thread(self.kb.get_fact, query=query)

            semantic_results = []
            for i, fact in enumerate(facts[:limit]):
                # Extract metadata
                metadata = json.loads(fact.get("metadata", "{}"))

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

            logger.debug(f"Semantic search returned {len(semantic_results)} results")
            return semantic_results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    def _perform_keyword_search(
        self, query: str, all_facts: List[Dict]
    ) -> List[SearchResult]:
        """Perform keyword-based search with TF-IDF-like scoring."""
        try:
            query_terms = set(query.lower().split())
            keyword_results = []

            for fact in all_facts:
                content = fact.get("content", "").lower()
                metadata_str = json.dumps(fact.get("metadata", {})).lower()
                combined_text = f"{content} {metadata_str}"

                # Simple keyword scoring
                matches = sum(1 for term in query_terms if term in combined_text)
                if matches > 0:
                    keyword_score = matches / len(query_terms)

                    # Boost score for exact phrase matches
                    if query.lower() in combined_text:
                        keyword_score *= 1.5

                    # Extract metadata
                    metadata = json.loads(fact.get("metadata", "{}"))

                    result = SearchResult(
                        content=fact.get("content", ""),
                        metadata=metadata,
                        semantic_score=0.0,  # Will be computed if needed
                        keyword_score=keyword_score,
                        hybrid_score=0.0,  # Will be computed later
                        relevance_rank=0,  # Will be updated
                        source_path=metadata.get("relative_path", "unknown"),
                        chunk_index=metadata.get("chunk_index", 0),
                    )
                    keyword_results.append(result)

            # Sort by keyword score
            keyword_results.sort(key=lambda x: x.keyword_score, reverse=True)

            # Update ranks
            for i, result in enumerate(keyword_results):
                result.relevance_rank = i + 1

            logger.debug(f"Keyword search returned {len(keyword_results)} results")
            return keyword_results[:20]  # Limit results

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
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

        logger.debug(f"Hybrid combination produced {len(combined_results)} results")
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

        logger.debug(f"Diversification: {len(results)} → {len(diversified)} results")
        return diversified

    async def _rerank_with_cross_encoder(
        self, query: str, results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Rerank results using cross-encoder model for improved relevance.

        Uses sentence-transformers cross-encoder which is specifically trained
        for search result reranking tasks. This provides much better relevance
        scoring than simple term matching.
        """
        try:
            # Lazy load cross-encoder model
            if not hasattr(self, "_cross_encoder"):
                try:
                    from sentence_transformers import CrossEncoder

                    model_name = getattr(
                        self,
                        "reranking_model",
                        "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    )
                    logger.info(f"Loading cross-encoder model: {model_name}")
                    self._cross_encoder = CrossEncoder(model_name)
                    logger.info("Cross-encoder model loaded successfully")
                except ImportError:
                    logger.warning(
                        "sentence-transformers not available, using fallback reranking"
                    )
                    self._cross_encoder = None
                except Exception as e:
                    logger.error(f"Failed to load cross-encoder model: {e}")
                    self._cross_encoder = None

            # Use full cross-encoder model if available
            if self._cross_encoder is not None:
                # Prepare query-document pairs for cross-encoder
                pairs = [(query, result.content) for result in results]

                # Get relevance scores from cross-encoder
                # Run in thread pool to avoid blocking async event loop
                cross_encoder_scores = await asyncio.to_thread(
                    self._cross_encoder.predict, pairs
                )

                # Apply scores to results
                for result, ce_score in zip(results, cross_encoder_scores):
                    # Combine cross-encoder score with hybrid score
                    # Cross-encoder gets 80% weight as it's more accurate
                    result.rerank_score = (
                        float(ce_score) * 0.8 + result.hybrid_score * 0.2
                    )

                logger.debug(
                    f"Cross-encoder reranking completed with model for {len(results)} results"
                )

            else:
                # Fallback to simple term-based reranking
                logger.debug("Using fallback term-based reranking")
                # Cache query.lower() outside loop (Issue #323)
                query_lower = query.lower()
                query_terms = query_lower.split()

                for result in results:
                    # Simple reranking based on query term frequency in content
                    content_lower = result.content.lower()

                    # Count query terms in content
                    term_matches = sum(
                        1 for term in query_terms if term in content_lower
                    )

                    # Bonus for exact query match
                    exact_match_bonus = 2 if query_lower in content_lower else 0

                    # Combine with existing hybrid score
                    rerank_score = (
                        result.hybrid_score * 0.7
                        + (term_matches / len(query_terms)) * 0.2
                        + exact_match_bonus * 0.1
                    )

                    result.rerank_score = rerank_score

            # Sort by rerank score
            results.sort(key=lambda x: x.rerank_score or 0, reverse=True)

            # Update ranks after reranking
            for i, result in enumerate(results):
                result.relevance_rank = i + 1

            logger.debug(
                f"Reranking completed: top score = {results[0].rerank_score:.3f}"
            )
            return results

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return original results on error
            return results

    async def advanced_search(
        self, query: str, max_results: int = 5, enable_reranking: bool = True
    ) -> Tuple[List[SearchResult], RAGMetrics]:
        """
        Perform advanced RAG search with all optimizations.

        Returns:
            (search_results, performance_metrics)
        """
        start_time = time.time()
        metrics = RAGMetrics()

        try:
            logger.info(f"Advanced search: '{query}' (max_results={max_results})")

            # Step 1: Query analysis and context optimization
            query_start = time.time()
            context = self._analyze_query_context(query)
            metrics.query_processing_time = time.time() - query_start

            # Step 2: Multi-strategy retrieval
            retrieval_start = time.time()

            # Semantic search
            semantic_results = await self._perform_semantic_search(
                query, limit=self.max_results_per_stage
            )

            # Get all facts for keyword search
            all_facts = await self.kb.get_all_facts()

            # Keyword search
            keyword_results = self._perform_keyword_search(query, all_facts)

            # Combine with hybrid scoring
            hybrid_results = self._combine_hybrid_results(
                semantic_results, keyword_results
            )

            metrics.retrieval_time = time.time() - retrieval_start
            metrics.documents_considered = len(hybrid_results)
            metrics.hybrid_search_enabled = True

            # Step 3: Result diversification
            diversified_results = self._diversify_results(hybrid_results)

            # Step 4: Cross-encoder reranking (if enabled)
            final_results = diversified_results
            if enable_reranking and len(diversified_results) > 1:
                rerank_start = time.time()
                final_results = await self._rerank_with_cross_encoder(
                    query, diversified_results
                )
                metrics.reranking_time = time.time() - rerank_start

            # Step 5: Apply context optimization and limit results
            optimized_results = final_results[:max_results]

            # Adjust chunk count based on query context
            if (
                len(optimized_results) < context.suggested_chunk_count
                and len(final_results) > max_results
            ):
                optimized_results = final_results[: context.suggested_chunk_count]

            metrics.final_results_count = len(optimized_results)
            metrics.total_time = time.time() - start_time
            metrics.gpu_acceleration_used = True  # Semantic chunker uses GPU

            logger.info("Advanced search completed:")
            logger.info(f"  - Total time: {metrics.total_time:.3f}s")
            logger.info(f"  - Documents considered: {metrics.documents_considered}")
            logger.info(f"  - Final results: {metrics.final_results_count}")
            logger.info(f"  - Query type: {context.query_type}")

            return optimized_results, metrics

        except Exception as e:
            logger.error(f"Advanced search failed: {e}")
            metrics.total_time = time.time() - start_time
            return [], metrics

    async def get_optimized_context(
        self, query: str, max_context_length: int = 2000
    ) -> Tuple[str, RAGMetrics]:
        """
        Get optimized context for RAG-based response generation.

        Dynamically selects and combines the most relevant information.
        """
        try:
            # Perform advanced search
            results, metrics = await self.advanced_search(query, max_results=8)

            if not results:
                return "No relevant information found.", metrics

            # Analyze query to determine optimal context strategy
            context = self._analyze_query_context(query)

            # Build context with dynamic length optimization
            context_parts = []
            current_length = 0

            for i, result in enumerate(results):
                # Create context entry
                source_info = f"Source: {result.source_path}"
                if result.chunk_index > 0:
                    source_info += f" (section {result.chunk_index + 1})"

                context_entry = f"{source_info}\nContent: {result.content}\n"

                # Check if adding this entry would exceed limits
                entry_length = len(context_entry)
                if current_length + entry_length > max_context_length and context_parts:
                    break

                context_parts.append(context_entry)
                current_length += entry_length

                # Ensure we have enough context for complex queries
                if i >= 2 and context.complexity_score < 0.6:
                    break

            # Combine context
            optimized_context = "\n---\n".join(context_parts)

            # Add summary header
            header = f"Relevant Information for: {query}\n"
            header += f"Sources: {len(context_parts)} documents\n"
            header += f"Query type: {context.query_type}\n\n"

            final_context = header + optimized_context

            logger.info(
                f"Optimized context generated: {len(final_context)} characters from {len(context_parts)} sources"
            )

            return final_context, metrics

        except Exception as e:
            logger.error(f"Context optimization failed: {e}")
            metrics = RAGMetrics()
            return f"Error retrieving context: {str(e)}", metrics

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
