# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Search Response Builder Module

Issue #381: Extracted from search.py god class refactoring.
Contains response building and clustering functionality.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.models.task_context import SearchResponseContext

logger = logging.getLogger(__name__)


class ResponseBuilder:
    """
    Builds search response dictionaries.

    Handles result pagination, clustering, and response formatting.
    """

    def build_empty_query_response(self) -> Dict[str, Any]:
        """Build response for empty query. Issue #281: Extracted helper."""
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "message": "Empty query",
        }

    def build_success_response(
        self,
        results: List[Dict[str, Any]],
        total_count: int,
        offset: int,
        limit: int,
        processed_query: str,
        mode: str,
        tags: Optional[List[str]],
        min_score: float,
        enable_reranking: bool,
    ) -> Dict[str, Any]:
        """Build successful search response. Issue #281: Extracted helper."""
        return {
            "success": True,
            "results": results[offset : offset + limit],
            "total_count": total_count,
            "query_processed": processed_query,
            "mode": mode,
            "tags_applied": tags if tags else [],
            "min_score_applied": min_score,
            "reranking_applied": enable_reranking,
        }

    def cluster_search_results(
        self,
        results: List[Dict[str, Any]],
        enable_clustering: bool,
        offset: int,
        limit: int,
    ) -> Tuple[Optional[List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """
        Cluster search results by topic.

        Issue #281: Extracted from enhanced_search_v2 for clarity.

        Args:
            results: Search results to cluster
            enable_clustering: Whether to enable clustering
            offset: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (clusters, unclustered_results)
        """
        if not enable_clustering or not results:
            return None, results

        from src.knowledge.search_quality import get_result_clusterer

        clusterer = get_result_clusterer()
        cluster_objects, unclustered = clusterer.cluster_results(results)
        clusters = [
            {
                "topic": c.topic,
                "keywords": c.keywords,
                "avg_score": c.avg_score,
                "result_count": len(c.results),
                "results": c.results[offset : offset + limit],
            }
            for c in cluster_objects
        ]
        return clusters, unclustered

    def build_enhanced_response(
        self,
        results: List[Dict[str, Any]],
        unclustered: List[Dict[str, Any]],
        clusters: Optional[List[Dict[str, Any]]],
        query: str,
        mode: str,
        tags: Optional[List[str]],
        min_score: float,
        enable_reranking: bool,
        enable_query_expansion: bool,
        enable_relevance_scoring: bool,
        enable_clustering: bool,
        queries_count: int,
        duration_ms: int,
        offset: int,
        limit: int,
    ) -> Dict[str, Any]:
        """
        Build the enhanced search response.

        Issue #281: Extracted from enhanced_search_v2 for clarity.
        Issue #375: Delegates to build_enhanced_response_ctx using
        SearchResponseContext for backward compatibility.

        Args:
            results: All search results
            unclustered: Unclustered results
            clusters: Clustered results (if enabled)
            query: Processed query
            mode: Search mode
            tags: Applied tags
            min_score: Minimum score threshold
            enable_reranking: Whether reranking was applied
            enable_query_expansion: Whether query expansion was applied
            enable_relevance_scoring: Whether relevance scoring was applied
            enable_clustering: Whether clustering was applied
            queries_count: Number of query variations searched
            duration_ms: Search duration in milliseconds
            offset: Pagination offset
            limit: Pagination limit

        Returns:
            Enhanced search response dictionary
        """
        # Issue #375: Create context and delegate
        ctx = SearchResponseContext(
            results=results,
            unclustered=unclustered,
            clusters=clusters,
            query_processed=query,
            mode=mode,
            tags=tags,
            min_score=min_score,
            enable_reranking=enable_reranking,
            enable_query_expansion=enable_query_expansion,
            enable_relevance_scoring=enable_relevance_scoring,
            enable_clustering=enable_clustering,
            queries_count=queries_count,
            duration_ms=duration_ms,
            offset=offset,
            limit=limit,
        )
        return self.build_enhanced_response_ctx(ctx)

    def build_enhanced_response_ctx(self, ctx: SearchResponseContext) -> Dict[str, Any]:
        """
        Build the enhanced search response using context.

        Issue #375: Refactored from 15-parameter signature to accept a single
        SearchResponseContext object.

        Args:
            ctx: SearchResponseContext containing all response parameters.

        Returns:
            Enhanced search response dictionary
        """
        total_count = len(ctx.results)
        paginated_results = (
            ctx.unclustered[ctx.offset : ctx.offset + ctx.limit]
            if not ctx.enable_clustering
            else ctx.unclustered
        )

        response = {
            "success": True,
            "results": paginated_results,
            "total_count": total_count,
            "query_processed": ctx.query_processed,
            "mode": ctx.mode,
            "tags_applied": ctx.tags if ctx.tags else [],
            "min_score_applied": ctx.min_score,
            "reranking_applied": ctx.enable_reranking,
            "search_duration_ms": ctx.duration_ms,
            "query_expansion_applied": ctx.enable_query_expansion,
            "queries_searched": ctx.queries_count if ctx.enable_query_expansion else 1,
            "relevance_scoring_applied": ctx.enable_relevance_scoring,
        }

        if ctx.enable_clustering and ctx.clusters:
            response["clusters"] = ctx.clusters
            response["unclustered_count"] = len(ctx.unclustered)

        return response


# Module-level instance for convenience
_response_builder = None


def get_response_builder() -> ResponseBuilder:
    """Get the shared ResponseBuilder instance."""
    global _response_builder
    if _response_builder is None:
        _response_builder = ResponseBuilder()
    return _response_builder
