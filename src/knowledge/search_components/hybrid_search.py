# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hybrid Search Module

Issue #381: Extracted from search.py god class refactoring.
Contains hybrid search with Reciprocal Rank Fusion (RRF).
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class HybridSearcher:
    """
    Performs hybrid search combining semantic and keyword results.

    Uses Reciprocal Rank Fusion (RRF) to combine rankings from
    different search methods for improved relevance.
    """

    # Standard RRF constant
    RRF_K = 60

    def __init__(
        self,
        semantic_search_func: Callable[..., Coroutine],
        keyword_search_func: Callable[..., Coroutine],
    ):
        """
        Initialize hybrid searcher.

        Args:
            semantic_search_func: Async function for semantic search
            keyword_search_func: Async function for keyword search
        """
        self.semantic_search = semantic_search_func
        self.keyword_search = keyword_search_func

    def process_rrf_results(
        self,
        results: List[Dict[str, Any]],
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        k: int,
        prefix: str,
    ) -> None:
        """Process results for RRF scoring. Issue #281: Extracted helper."""
        for rank, result in enumerate(results):
            fact_id = (
                result.get("metadata", {}).get("fact_id")
                or result.get("node_id", f"{prefix}_{rank}")
            )
            rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
            if fact_id not in result_map:
                result_map[fact_id] = result

    def build_rrf_results(
        self,
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Build final RRF-ranked results. Issue #281: Extracted helper."""
        sorted_ids = sorted(
            rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
        )
        max_rrf = max(rrf_scores.values()) if rrf_scores else 1
        results = []
        for fact_id in sorted_ids[:limit]:
            result = result_map[fact_id].copy()
            result["score"] = rrf_scores[fact_id] / max_rrf
            result["rrf_score"] = rrf_scores[fact_id]
            results.append(result)
        return results

    async def search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword results.

        Issue #281 refactor: Uses RRF with k=60 for fusion.

        Args:
            query: Search query
            limit: Maximum results to return
            category: Optional category filter

        Returns:
            Combined and ranked search results
        """
        try:
            # Run both searches in parallel
            semantic_task = asyncio.create_task(
                self.semantic_search(
                    query,
                    top_k=limit,
                    filters={"category": category} if category else None,
                    mode="vector",
                )
            )
            keyword_task = asyncio.create_task(
                self.keyword_search(query, limit, category)
            )
            semantic_results, keyword_results = await asyncio.gather(
                semantic_task, keyword_task
            )

            # Reciprocal Rank Fusion
            rrf_scores: Dict[str, float] = {}
            result_map: Dict[str, Dict[str, Any]] = {}

            self.process_rrf_results(
                semantic_results, rrf_scores, result_map, self.RRF_K, "sem"
            )
            self.process_rrf_results(
                keyword_results, rrf_scores, result_map, self.RRF_K, "kw"
            )

            return self.build_rrf_results(rrf_scores, result_map, limit)

        except Exception as e:
            logger.error("Hybrid search failed: %s", e)
            # Fallback to semantic search
            return await self.semantic_search(query, top_k=limit, mode="vector")
