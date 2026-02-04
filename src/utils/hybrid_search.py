# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hybrid Search Implementation
Combines semantic search with keyword-based search for improved relevance and coverage.
"""

import logging
import math
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.config import UnifiedConfigManager

# Create singleton config instance
config = UnifiedConfigManager()

# Issue #380: Pre-compiled regex for word extraction
_WORD_BOUNDARY_RE = re.compile(r"\b[a-zA-Z0-9]+\b")


def _build_word_frequency_map(text: str) -> Dict[str, int]:
    """
    Build a frequency map of words in the given text.

    Issue #620: Extracted from calculate_keyword_score to reduce function length.

    Args:
        text: Document text to analyze

    Returns:
        Dictionary mapping words to their occurrence counts
    """
    words = _WORD_BOUNDARY_RE.findall(text.lower())
    word_count: Dict[str, int] = defaultdict(int)
    for word in words:
        word_count[word] += 1
    return word_count


def _calculate_single_keyword_score(
    keyword: str,
    word_count: Dict[str, int],
    total_words: int,
    document_metadata: Dict[str, Any],
) -> float:
    """
    Calculate relevance score for a single keyword in a document.

    Issue #620: Extracted from calculate_keyword_score to reduce function length.

    Args:
        keyword: The keyword to score
        word_count: Word frequency map for the document
        total_words: Total word count in document
        document_metadata: Document metadata for source boost

    Returns:
        Score between 0.0 and 1.0 for this keyword
    """
    keyword_lower = keyword.lower()
    keyword_count = word_count.get(keyword_lower, 0)

    if keyword_count > 0:
        # TF-IDF-like scoring
        tf = keyword_count / total_words  # Term frequency

        # Boost score for exact matches in title/source
        title_boost = 1.0
        source = document_metadata.get("source", "").lower()
        if keyword_lower in source:
            title_boost = 2.0

        # Boost score for multiple occurrences
        frequency_boost = min(math.log(keyword_count + 1), 2.0)

        return tf * title_boost * frequency_boost

    # Check for partial matches
    document_words = list(word_count.keys())
    partial_matches = [
        word
        for word in document_words
        if keyword_lower in word or word in keyword_lower
    ]
    if partial_matches:
        return len(partial_matches) / total_words * 0.5

    return 0.0


class HybridSearchEngine:
    """
    Hybrid search engine that combines semantic and keyword-based search.
    Uses weighted scoring to balance between semantic similarity and keyword relevance.
    """

    def __init__(self, knowledge_base=None):
        """Initialize hybrid search with knowledge base and weighted scoring config."""
        self.logger = logging.getLogger(__name__)
        self.knowledge_base = knowledge_base

        # Configuration from config files
        self.semantic_weight = config.get("search.hybrid.semantic_weight", 0.7)
        self.keyword_weight = config.get("search.hybrid.keyword_weight", 0.3)
        self.min_keyword_score = config.get("search.hybrid.min_keyword_score", 0.1)
        self.keyword_boost_factor = config.get(
            "search.hybrid.keyword_boost_factor", 1.5
        )

        # Search parameters
        self.semantic_top_k = config.get("search.hybrid.semantic_top_k", 15)
        self.final_top_k = config.get("search.hybrid.final_top_k", 10)

        # Keyword extraction settings
        self.stop_words = set(
            config.get(
                "search.hybrid.stop_words",
                [
                    "the",
                    "a",
                    "an",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                    "from",
                    "up",
                    "about",
                    "into",
                    "through",
                    "during",
                    "is",
                    "are",
                    "was",
                    "were",
                    "be",
                    "been",
                    "being",
                    "have",
                    "has",
                    "had",
                    "do",
                    "does",
                    "did",
                    "will",
                    "would",
                    "could",
                    "should",
                    "may",
                    "might",
                ],
            )
        )

        self.min_keyword_length = config.get("search.hybrid.min_keyword_length", 3)

    def extract_keywords(self, text: str) -> List[str]:
        """Extract meaningful keywords from text."""
        # Convert to lowercase and split into words (Issue #380: use pre-compiled pattern)
        words = _WORD_BOUNDARY_RE.findall(text.lower())

        # Filter out stop words and short words
        keywords = [
            word
            for word in words
            if word not in self.stop_words and len(word) >= self.min_keyword_length
        ]

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for keyword in keywords:
            if keyword not in seen:
                seen.add(keyword)
                unique_keywords.append(keyword)

        return unique_keywords

    def calculate_keyword_score(
        self,
        query_keywords: List[str],
        document_text: str,
        document_metadata: Dict[str, Any],
    ) -> float:
        """
        Calculate keyword-based relevance score for a document.

        Issue #620: Refactored to use extracted helper functions.
        """
        if not query_keywords:
            return 0.0

        # Issue #620: Use helper to build word frequency map
        word_count = _build_word_frequency_map(document_text)
        total_words = sum(word_count.values())

        if total_words == 0:
            return 0.0

        # Issue #620: Calculate score for each keyword using helper
        keyword_scores = [
            _calculate_single_keyword_score(
                keyword, word_count, total_words, document_metadata
            )
            for keyword in query_keywords
        ]

        # Average keyword score with emphasis on matches
        if keyword_scores:
            # Give more weight to documents that match more keywords
            match_ratio = sum(1 for score in keyword_scores if score > 0) / len(
                keyword_scores
            )
            avg_score = sum(keyword_scores) / len(keyword_scores)

            # Boost documents that match multiple keywords
            final_score = avg_score * (1 + match_ratio * self.keyword_boost_factor)
            return min(final_score, 1.0)  # Cap at 1.0

        return 0.0

    def combine_scores(self, semantic_score: float, keyword_score: float) -> float:
        """Combine semantic and keyword scores using weighted average."""
        # Normalize scores to [0, 1] range
        semantic_score = max(0.0, min(1.0, semantic_score))
        keyword_score = max(0.0, min(1.0, keyword_score))

        # Apply minimum threshold for keyword score
        if keyword_score < self.min_keyword_score:
            keyword_score = 0.0

        # Weighted combination
        combined_score = (
            self.semantic_weight * semantic_score + self.keyword_weight * keyword_score
        )

        return combined_score

    def _is_near_duplicate(
        self, content: str, unique_results: List[Dict[str, Any]], threshold: float
    ) -> bool:
        """Check if content is a near-duplicate of any existing result. (Issue #315)"""
        content_words = set(content.lower().split())
        if not content_words:
            return False
        for unique_result in unique_results:
            existing_content = unique_result.get("content", "").strip()
            if not existing_content:
                continue
            existing_words = set(existing_content.lower().split())
            if not existing_words:
                continue
            intersection = len(content_words & existing_words)
            union = len(content_words | existing_words)
            jaccard_similarity = intersection / union if union > 0 else 0.0
            if jaccard_similarity > threshold:
                return True
        return False

    def deduplicate_results(
        self, results: List[Dict[str, Any]], similarity_threshold: float = 0.9
    ) -> List[Dict[str, Any]]:
        """Remove duplicate or very similar results. (Issue #315 - uses helper)"""
        if not results:
            return results

        unique_results = []
        seen_contents = set()

        for result in results:
            content = result.get("content", "").strip()
            if not content:
                continue

            # Check for exact duplicates
            content_hash = hash(content)
            if content_hash in seen_contents:
                continue

            # Check for near-duplicates using helper
            if self._is_near_duplicate(content, unique_results, similarity_threshold):
                continue

            seen_contents.add(content_hash)
            unique_results.append(result)

        return unique_results

    def _enhance_result_with_scores(
        self,
        result: Dict[str, Any],
        query_keywords: List[str],
    ) -> Dict[str, Any]:
        """Enhance a single result with hybrid scoring (Issue #665: extracted helper).

        Args:
            result: Original search result
            query_keywords: Keywords extracted from query

        Returns:
            Enhanced result with hybrid, semantic, and keyword scores
        """
        content = result.get("content", "")
        metadata = result.get("metadata", {})
        semantic_score = result.get("score", 0.0)

        # Calculate keyword score
        keyword_score = self.calculate_keyword_score(query_keywords, content, metadata)

        # Combine scores
        hybrid_score = self.combine_scores(semantic_score, keyword_score)

        # Create enhanced result
        return {
            **result,  # Copy original result
            "hybrid_score": hybrid_score,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "matched_keywords": [
                kw for kw in query_keywords if kw.lower() in content.lower()
            ],
        }

    async def _fallback_semantic_search(
        self, query: str, top_k: int, filters: Optional[Dict], error: Exception
    ) -> List[Dict[str, Any]]:
        """
        Fallback to regular semantic search when hybrid search fails.

        Issue #620.
        """
        self.logger.error("Error in hybrid search: %s", error)
        try:
            return await self.knowledge_base.search(query, top_k, filters)
        except Exception as fallback_error:
            self.logger.error("Fallback search also failed: %s", fallback_error)
            return []

    async def search(
        self, query: str, top_k: int = 10, filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword-based approaches.

        Args:
            query: Search query string
            top_k: Number of results to return
            filters: Optional filters for the search

        Returns:
            List of search results with hybrid scores

        Issue #620: Refactored to use extracted helper methods.
        """
        if not self.knowledge_base:
            self.logger.error("Knowledge base not available for hybrid search")
            return []

        try:
            # Extract keywords from query
            query_keywords = self.extract_keywords(query)
            self.logger.debug("Extracted keywords from '%s': %s", query, query_keywords)

            # Perform semantic search with higher top_k to get more candidates
            semantic_results = await self.knowledge_base.search(
                query, top_k=self.semantic_top_k, filters=filters
            )

            if not semantic_results:
                self.logger.warning("No semantic results found for query: '%s'", query)
                return []

            # Enhance results with keyword scoring
            enhanced_results = [
                self._enhance_result_with_scores(result, query_keywords)
                for result in semantic_results
            ]

            # Sort by hybrid score (descending)
            enhanced_results.sort(key=lambda x: x["hybrid_score"], reverse=True)

            # Update the main score field with hybrid score
            for result in enhanced_results:
                result["score"] = result["hybrid_score"]

            # Deduplicate and return top results
            unique_results = self.deduplicate_results(enhanced_results)
            final_results = unique_results[: min(top_k, self.final_top_k)]

            self.logger.info(
                f"Hybrid search for '{query}': "
                f"{len(semantic_results)} semantic -> {len(unique_results)} unique -> "
                f"{len(final_results)} final results"
            )

            return final_results

        except Exception as e:
            return await self._fallback_semantic_search(query, top_k, filters, e)

    async def explain_search(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Perform a search and return detailed explanation of the scoring process.
        Useful for debugging and understanding search behavior.
        """
        try:
            query_keywords = self.extract_keywords(query)

            # Get semantic results
            semantic_results = await self.knowledge_base.search(
                query, top_k=min(top_k * 2, 20)
            )

            explanation = {
                "query": query,
                "extracted_keywords": query_keywords,
                "semantic_weight": self.semantic_weight,
                "keyword_weight": self.keyword_weight,
                "semantic_results_count": len(semantic_results),
                "scoring_details": [],
            }

            for i, result in enumerate(semantic_results[:top_k]):
                content = (
                    result.get("content", "")[:200] + "..."
                )  # Truncate for readability
                semantic_score = result.get("score", 0.0)

                keyword_score = self.calculate_keyword_score(
                    query_keywords,
                    result.get("content", ""),
                    result.get("metadata", {}),
                )

                hybrid_score = self.combine_scores(semantic_score, keyword_score)

                matched_keywords = [
                    kw
                    for kw in query_keywords
                    if kw.lower() in result.get("content", "").lower()
                ]

                score_detail = {
                    "rank": i + 1,
                    "content_preview": content,
                    "semantic_score": round(semantic_score, 4),
                    "keyword_score": round(keyword_score, 4),
                    "hybrid_score": round(hybrid_score, 4),
                    "matched_keywords": matched_keywords,
                    "source": result.get("metadata", {}).get("source", "unknown"),
                }

                explanation["scoring_details"].append(score_detail)

            return explanation

        except Exception as e:
            self.logger.error("Error in search explanation: %s", e)
            return {"error": str(e)}


# Global instance (thread-safe)
import threading

_hybrid_search_engine = None
_hybrid_search_engine_lock = threading.Lock()


def get_hybrid_search_engine(knowledge_base=None) -> HybridSearchEngine:
    """Get the global hybrid search engine instance (thread-safe)."""
    global _hybrid_search_engine
    if _hybrid_search_engine is None:
        with _hybrid_search_engine_lock:
            # Double-check after acquiring lock
            if _hybrid_search_engine is None:
                _hybrid_search_engine = HybridSearchEngine(knowledge_base)
    elif knowledge_base and _hybrid_search_engine.knowledge_base != knowledge_base:
        # Update knowledge base reference
        _hybrid_search_engine.knowledge_base = knowledge_base
    return _hybrid_search_engine
