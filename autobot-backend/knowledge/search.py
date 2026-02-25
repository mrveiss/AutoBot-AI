# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Search Module

Issue #381: This file has been refactored into the search_components/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/knowledge/search_components/
- helpers.py: Redis hash operations and result building
- query_processor.py: Query preprocessing and expansion
- keyword_search.py: Keyword-based search using Redis
- hybrid_search.py: Hybrid search with RRF
- reranking.py: Cross-encoder result reranking
- tag_filter.py: Tag-based result filtering
- analytics.py: Search analytics tracking
- response_builder.py: Response building and clustering

Note: Package is named search_components to avoid conflict with search.py.

Contains the SearchMixin class for all search-related functionality including
semantic search, keyword search, hybrid search, and query preprocessing.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

# Import components from the search_components package
from knowledge.search_components import (
    KeywordSearcher,
    QueryProcessor,
    ResponseBuilder,
    TagFilter,
    get_analytics,
    get_reranker,
)
from knowledge.search_components.helpers import (
    build_search_result,
    decode_redis_hash,
    matches_category,
    score_fact_by_terms,
)
from knowledge.search_components.hybrid_search import HybridSearcher
from models.task_context import EnhancedSearchContext

from autobot_shared.error_boundaries import error_boundary

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)

# Re-export helper functions for backward compatibility
_decode_redis_hash = decode_redis_hash
_matches_category = matches_category
_score_fact_by_terms = score_fact_by_terms
_build_search_result = build_search_result


class SearchMixin:
    """
    Search functionality mixin for knowledge base.

    Issue #381: Refactored to use focused search package components.

    Provides comprehensive search capabilities:
    - Semantic (vector) search with ChromaDB
    - Keyword (text) search with Redis
    - Hybrid search with reciprocal rank fusion (RRF)
    - Query preprocessing and expansion
    - Tag-based filtering
    - Result reranking with cross-encoder
    - Score thresholding and pagination

    Key Features:
    - Issue #65: Embedding cache for query optimization
    - Issue #78: Enhanced search quality with preprocessing
    - Deduplication of chunked results
    - Multiple search modes (semantic, keyword, hybrid)
    """

    # Type hints for attributes from base class
    vector_store: "ChromaVectorStore"
    aioredis_client: "aioredis.Redis"
    redis_client: "redis.Redis"
    initialized: bool

    def __init__(self, *args, **kwargs):
        """Initialize search mixin components."""
        super().__init__(*args, **kwargs)
        self._query_processor = QueryProcessor()
        self._response_builder = ResponseBuilder()
        self._tag_filter = None
        self._keyword_searcher = None
        self._hybrid_searcher = None

    def _get_tag_filter(self) -> TagFilter:
        """Lazy initialization of tag filter."""
        if self._tag_filter is None:
            self._tag_filter = TagFilter(getattr(self, "aioredis_client", None))
        return self._tag_filter

    def _get_keyword_searcher(self) -> KeywordSearcher:
        """Lazy initialization of keyword searcher."""
        if self._keyword_searcher is None:
            self._keyword_searcher = KeywordSearcher(
                getattr(self, "aioredis_client", None)
            )
        return self._keyword_searcher

    def _get_hybrid_searcher(self) -> HybridSearcher:
        """Lazy initialization of hybrid searcher."""
        if self._hybrid_searcher is None:
            self._hybrid_searcher = HybridSearcher(
                self.search,
                self._keyword_search,
            )
        return self._hybrid_searcher

    def _validate_search_inputs(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Validate search inputs, return empty list if invalid (Issue #398: extracted)."""
        if not query.strip():
            return []
        if not self.vector_store:
            logger.warning("Vector store not available for search")
            return []
        return None  # Valid inputs

    async def _execute_vector_search(
        self,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute vector search and deduplicate results (Issue #398: extracted)."""
        query_embedding = await self._get_query_embedding(query)
        results_data = await self._query_chromadb(
            query_embedding, similarity_top_k, where=filters
        )
        results = self._deduplicate_results(results_data, similarity_top_k)
        logger.info(
            "ChromaDB search returned %d unique documents for query: %s...",
            len(results),
            query[:50],
        )
        return results

    async def search(
        self,
        query: str,
        top_k: int = 10,
        similarity_top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base (Issue #398: refactored).

        Issue #934: filters is now passed to ChromaDB as a metadata where clause.
        """
        self.ensure_initialized()
        similarity_top_k = similarity_top_k or top_k

        invalid_result = self._validate_search_inputs(query)
        if invalid_result is not None:
            return invalid_result

        try:
            return await self._execute_vector_search(
                query, similarity_top_k, filters=filters
            )
        except Exception as e:
            logger.error("Knowledge base search failed: %s", e)
            return []

    async def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for query, using cache when available.

        Issue #281: Extracted helper.
        Issue #165: Uses NPU worker for hardware-accelerated embedding generation.
        """
        from knowledge.embedding_cache import get_embedding_cache
        from knowledge.facts import _generate_embedding_with_npu_fallback

        _embedding_cache = get_embedding_cache()
        query_embedding = await _embedding_cache.get(query)

        if query_embedding is None:
            # Cache miss - compute embedding using NPU worker with fallback
            query_embedding = await _generate_embedding_with_npu_fallback(query)
            await _embedding_cache.put(query, query_embedding)

        return query_embedding

    async def _query_chromadb(
        self,
        query_embedding: List[float],
        similarity_top_k: int,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Query ChromaDB directly with embedding. Issue #281: Extracted helper.

        Issue #934: Accepts optional where filter for permission-based pre-filtering.
        """
        chroma_collection = self.vector_store._collection
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": similarity_top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        try:
            return await asyncio.to_thread(chroma_collection.query, **kwargs)
        except (ValueError, Exception) as exc:
            # ChromaDB raises ValueError when where filter matches fewer docs
            # than n_results. Fall back to unfiltered search.
            logger.warning(
                "ChromaDB where filter failed (%s), retrying without filter", exc
            )
            kwargs.pop("where", None)
            return await asyncio.to_thread(chroma_collection.query, **kwargs)

    def _deduplicate_results(
        self, results_data: Dict[str, Any], similarity_top_k: int
    ) -> List[Dict[str, Any]]:
        """Deduplicate and format ChromaDB results. Issue #281: Extracted helper."""
        seen_documents: Dict[str, Dict[str, Any]] = {}

        if not (
            results_data
            and "documents" in results_data
            and results_data["documents"][0]
        ):
            return []

        for i, doc in enumerate(results_data["documents"][0]):
            score = self._calculate_similarity_score(results_data, i)
            metadata = (
                results_data["metadatas"][0][i] if "metadatas" in results_data else {}
            )
            doc_key = self._get_document_key(metadata, i)

            if (
                doc_key not in seen_documents
                or score > seen_documents[doc_key]["score"]
            ):
                seen_documents[doc_key] = self._build_result_dict(
                    doc, score, metadata, results_data, i
                )

        results = sorted(
            seen_documents.values(), key=lambda x: x["score"], reverse=True
        )
        return results[:similarity_top_k]

    def _calculate_similarity_score(
        self, results_data: Dict[str, Any], index: int
    ) -> float:
        """Convert distance to similarity score. Issue #281: Extracted helper."""
        distance = (
            results_data["distances"][0][index] if "distances" in results_data else 1.0
        )
        return max(0.0, 1.0 - (distance / 2.0))

    def _get_document_key(self, metadata: Dict[str, Any], index: int) -> str:
        """Get unique key for document deduplication. Issue #281: Extracted helper."""
        doc_key = metadata.get("fact_id")
        if not doc_key:
            title = metadata.get("title", "")
            category = metadata.get("category", "")
            doc_key = f"{category}:{title}" if (title or category) else f"doc_{index}"
        return doc_key

    def _build_result_dict(
        self,
        doc: str,
        score: float,
        metadata: Dict[str, Any],
        results_data: Dict[str, Any],
        index: int,
    ) -> Dict[str, Any]:
        """Build result dictionary for a search result. Issue #281: Extracted helper."""
        node_id = (
            results_data["ids"][0][index]
            if "ids" in results_data
            else f"result_{index}"
        )
        return {
            "content": doc,
            "score": score,
            "metadata": metadata,
            "node_id": node_id,
            "doc_id": node_id,  # V1 compatibility
        }

    async def _perform_search(
        self,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        mode: str,
    ) -> List[Dict[str, Any]]:
        """Internal search implementation with timeout protection (V1 compatibility)"""
        # Delegate to main search method
        return await self.search(
            query, similarity_top_k=similarity_top_k, filters=filters, mode=mode
        )

    def _build_empty_query_response(self) -> Dict[str, Any]:
        """Build response for empty query. Issue #281: Extracted helper."""
        return self._response_builder.build_empty_query_response()

    def _build_no_tags_match_response(self, processed_query: str) -> Dict[str, Any]:
        """Build response when no facts match tags. Issue #281: Extracted helper."""
        return {
            "success": True,
            "results": [],
            "total_count": 0,
            "query_processed": processed_query,
            "message": "No facts match the specified tags",
        }

    async def _get_tag_filtered_ids(
        self, tags: Optional[List[str]], tags_match_any: bool, processed_query: str
    ) -> tuple:
        """Get tag-filtered fact IDs. Returns (filtered_ids, early_return_response or None)."""
        return await self._get_tag_filter().get_tag_filtered_ids(
            tags, tags_match_any, processed_query
        )

    async def _execute_search_by_mode(
        self, mode: str, processed_query: str, fetch_limit: int, category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Execute search based on mode. Issue #281: Extracted helper."""
        if mode == "keyword":
            return await self._keyword_search(processed_query, fetch_limit, category)
        elif mode == "semantic":
            return await self.search(
                processed_query,
                top_k=fetch_limit,
                filters={"category": category} if category else None,
                mode="vector",
            )
        else:  # hybrid mode
            return await self._hybrid_search(processed_query, fetch_limit, category)

    def _apply_post_search_filters(
        self,
        results: List[Dict[str, Any]],
        tag_filtered_ids: Optional[Set[str]],
        min_score: float,
    ) -> List[Dict[str, Any]]:
        """Apply tag and score filtering to results. Issue #281: Extracted helper."""
        results = self._get_tag_filter().apply_tag_filter(results, tag_filtered_ids)
        if min_score > 0:
            results = [r for r in results if r.get("score", 0) >= min_score]
        return results

    def _build_success_response(
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
        return self._response_builder.build_success_response(
            results,
            total_count,
            offset,
            limit,
            processed_query,
            mode,
            tags,
            min_score,
            enable_reranking,
        )

    def _calculate_fetch_limit(
        self, limit: int, offset: int, tags: Optional[List[str]], min_score: float
    ) -> int:
        """Calculate fetch limit based on filters (Issue #398: extracted)."""
        multiplier = 3 if tags or min_score > 0 else 1.5
        return min(int((limit + offset) * multiplier), 500)

    async def _execute_enhanced_search_pipeline(
        self,
        processed_query: str,
        mode: str,
        category: Optional[str],
        fetch_limit: int,
        tag_filtered_ids: Optional[Set[str]],
        min_score: float,
        enable_reranking: bool,
    ) -> List[Dict[str, Any]]:
        """Execute search pipeline with filtering and reranking (Issue #398: extracted)."""
        results = await self._execute_search_by_mode(
            mode, processed_query, fetch_limit, category
        )
        results = self._apply_post_search_filters(results, tag_filtered_ids, min_score)
        if enable_reranking and results:
            results = await self._rerank_results(processed_query, results)
        return results

    @error_boundary(component="knowledge_base", function="enhanced_search")
    async def enhanced_search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tags_match_any: bool = False,
        mode: str = "hybrid",
        enable_reranking: bool = False,
        min_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Enhanced search with filtering and reranking (Issue #398: refactored)."""
        self.ensure_initialized()
        if not query.strip():
            return self._build_empty_query_response()

        try:
            processed_query = self._preprocess_query(query)
            tag_filtered_ids, early_return = await self._get_tag_filtered_ids(
                tags, tags_match_any, processed_query
            )
            if early_return:
                return early_return

            fetch_limit = self._calculate_fetch_limit(limit, offset, tags, min_score)
            results = await self._execute_enhanced_search_pipeline(
                processed_query,
                mode,
                category,
                fetch_limit,
                tag_filtered_ids,
                min_score,
                enable_reranking,
            )

            return self._build_success_response(
                results,
                len(results),
                offset,
                limit,
                processed_query,
                mode,
                tags,
                min_score,
                enable_reranking,
            )
        except Exception as e:
            logger.error("Enhanced search failed: %s", e)
            return {"success": False, "results": [], "total_count": 0, "error": str(e)}

    def _preprocess_query(self, query: str) -> str:
        """Preprocess search query for better results. Issue #78: Query preprocessing."""
        return self._query_processor.preprocess_query(query)

    def _decode_tag_results(self, tag_results: list) -> List[Set[str]]:
        """Decode tag results from Redis to sets of fact IDs. Issue #281: Extracted helper."""
        return self._get_tag_filter().decode_tag_results(tag_results)

    def _combine_tag_fact_sets(
        self, tag_fact_sets: List[Set[str]], match_all: bool
    ) -> Set[str]:
        """Combine fact sets based on match_all flag. Issue #281: Extracted helper."""
        return self._get_tag_filter().combine_tag_fact_sets(tag_fact_sets, match_all)

    async def _get_fact_ids_by_tags(
        self, tags: List[str], match_all: bool = True
    ) -> Dict[str, Any]:
        """Get fact IDs matching specified tags (Issue #281 refactor)."""
        return await self._get_tag_filter().get_fact_ids_by_tags(tags, match_all)

    async def _process_keyword_batch(
        self, keys: list, query_terms: Set[str], category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Process a batch of Redis keys for keyword search. Issue #281: Extracted helper."""
        return await self._get_keyword_searcher().process_keyword_batch(
            keys, query_terms, category
        )

    async def _keyword_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform keyword-based search using Redis (Issue #281 refactor)."""
        return await self._get_keyword_searcher().search(query, limit, category)

    def _process_rrf_results(
        self,
        results: List[Dict[str, Any]],
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        k: int,
        prefix: str,
    ) -> None:
        """Process results for RRF scoring. Issue #281: Extracted helper."""
        self._get_hybrid_searcher().process_rrf_results(
            results, rrf_scores, result_map, k, prefix
        )

    def _build_rrf_results(
        self,
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Build final RRF-ranked results. Issue #281: Extracted helper."""
        return self._get_hybrid_searcher().build_rrf_results(
            rrf_scores, result_map, limit
        )

    async def _hybrid_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search combining semantic and keyword results."""
        return await self._get_hybrid_searcher().search(query, limit, category)

    async def _ensure_cross_encoder(self):
        """Ensure cross-encoder model is loaded. Issue #281: Extracted helper."""
        return await get_reranker()._ensure_cross_encoder()

    def _apply_rerank_scores(self, results: List[Dict[str, Any]], scores: list) -> None:
        """Apply rerank scores to results. Issue #281: Extracted helper."""
        get_reranker()._apply_rerank_scores(results, scores)

    async def _rerank_results(
        self, query: str, results: List[Dict[str, Any]], top_k: int = None
    ) -> List[Dict[str, Any]]:
        """Rerank results using cross-encoder for improved relevance."""
        return await get_reranker().rerank(query, results, top_k)

    @error_boundary(component="knowledge_base", function="enhanced_search_v2")
    async def enhanced_search_v2(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tags_match_any: bool = False,
        mode: str = "hybrid",
        enable_reranking: bool = False,
        min_score: float = 0.0,
        enable_query_expansion: bool = False,
        enable_relevance_scoring: bool = False,
        enable_clustering: bool = False,
        track_analytics: bool = True,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        exclude_terms: Optional[List[str]] = None,
        require_terms: Optional[List[str]] = None,
        exclude_sources: Optional[List[str]] = None,
        verified_only: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enhanced search v2 with full Issue #78 improvements."""
        ctx = EnhancedSearchContext.from_params(
            query=query,
            limit=limit,
            offset=offset,
            category=category,
            tags=tags,
            tags_match_any=tags_match_any,
            mode=mode,
            enable_reranking=enable_reranking,
            min_score=min_score,
            enable_query_expansion=enable_query_expansion,
            enable_relevance_scoring=enable_relevance_scoring,
            enable_clustering=enable_clustering,
            track_analytics=track_analytics,
            created_after=created_after,
            created_before=created_before,
            exclude_terms=exclude_terms,
            require_terms=require_terms,
            exclude_sources=exclude_sources,
            verified_only=verified_only,
            session_id=session_id,
        )
        return await self.enhanced_search_v2_ctx(ctx)

    def _extract_search_params(self, ctx: EnhancedSearchContext) -> Dict[str, Any]:
        """Extract search parameters from context (Issue #398: extracted)."""
        return {
            "query": ctx.query_params.query,
            "limit": ctx.query_params.limit,
            "offset": ctx.query_params.offset,
            "tags": ctx.query_params.tags,
            "tags_match_any": ctx.query_params.tags_match_any,
            "exclude_terms": ctx.query_params.exclude_terms,
            "require_terms": ctx.query_params.require_terms,
            "category": ctx.filters.category,
            "created_after": ctx.filters.created_after,
            "created_before": ctx.filters.created_before,
            "exclude_sources": ctx.filters.exclude_sources,
            "verified_only": ctx.filters.verified_only,
            "mode": ctx.options.mode,
            "enable_reranking": ctx.options.enable_reranking,
            "min_score": ctx.options.min_score,
            "enable_query_expansion": ctx.options.enable_query_expansion,
            "enable_relevance_scoring": ctx.options.enable_relevance_scoring,
            "enable_clustering": ctx.options.enable_clustering,
            "track_analytics": ctx.options.track_analytics,
            "session_id": ctx.session_id,
        }

    async def _execute_multi_query_search(
        self,
        queries: List[str],
        mode: str,
        fetch_limit: int,
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Execute search across multiple query variations (Issue #398: extracted)."""
        all_results: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()

        for search_query in queries:
            query_results = await self._execute_search_by_mode(
                mode, search_query, fetch_limit, category
            )
            for result in query_results:
                result_id = result.get("metadata", {}).get("fact_id") or result.get(
                    "node_id", ""
                )
                if result_id not in seen_ids:
                    seen_ids.add(result_id)
                    result["matched_query"] = search_query
                    all_results.append(result)

        return all_results

    async def _apply_all_search_filters(
        self,
        results: List[Dict[str, Any]],
        params: Dict[str, Any],
        tag_filtered_ids: Optional[Set[str]],
        processed_query: str,
        fetch_limit: int,
    ) -> List[Dict[str, Any]]:
        """Apply all filters and reranking to results (Issue #398: extracted)."""
        # Apply tag and score filters
        results = self._apply_post_search_filters(
            results, tag_filtered_ids, params["min_score"]
        )
        # Apply advanced filters
        results = self._apply_advanced_search_filters(
            results,
            params["created_after"],
            params["created_before"],
            params["exclude_terms"],
            params["require_terms"],
            params["exclude_sources"],
            params["verified_only"],
            params["min_score"],
            fetch_limit,
        )
        # Relevance scoring
        results = self._apply_relevance_scoring(
            results, processed_query, params["enable_relevance_scoring"]
        )
        # Reranking
        if params["enable_reranking"] and results:
            results = await self._rerank_results(processed_query, results)

        return results

    def _finalize_search_response(
        self,
        results: List[Dict[str, Any]],
        params: Dict[str, Any],
        processed_query: str,
        queries_count: int,
        duration_ms: int,
    ) -> Dict[str, Any]:
        """Finalize search with analytics, clustering, and response (Issue #398: extracted)."""
        # Analytics tracking
        self._track_search_analytics(
            params["query"],
            len(results),
            duration_ms,
            params["session_id"],
            params["mode"],
            params["tags"],
            params["category"],
            params["enable_query_expansion"],
            params["enable_relevance_scoring"],
            params["track_analytics"],
        )
        # Clustering
        clusters, unclustered = self._cluster_search_results(
            results, params["enable_clustering"], params["offset"], params["limit"]
        )
        # Build response
        return self._build_enhanced_search_response(
            results,
            unclustered,
            clusters,
            processed_query,
            params["mode"],
            params["tags"],
            params["min_score"],
            params["enable_reranking"],
            params["enable_query_expansion"],
            params["enable_relevance_scoring"],
            params["enable_clustering"],
            queries_count,
            duration_ms,
            params["offset"],
            params["limit"],
        )

    @error_boundary(component="knowledge_base", function="enhanced_search_v2_ctx")
    async def enhanced_search_v2_ctx(
        self, ctx: EnhancedSearchContext
    ) -> Dict[str, Any]:
        """Enhanced search v2 using EnhancedSearchContext (Issue #398: refactored)."""
        self.ensure_initialized()

        params = self._extract_search_params(ctx)
        if not params["query"].strip():
            return self._build_empty_query_response()

        start_time = time.time()

        try:
            processed_query = self._preprocess_query(params["query"])
            queries_to_search = self._expand_query_terms(
                processed_query, params["enable_query_expansion"]
            )

            tag_filtered_ids, early_return = await self._get_tag_filtered_ids(
                params["tags"], params["tags_match_any"], processed_query
            )
            if early_return:
                return early_return

            fetch_multiplier = (
                3
                if (
                    params["tags"] or params["min_score"] > 0 or params["exclude_terms"]
                )
                else 1.5
            )
            fetch_limit = min(
                int((params["limit"] + params["offset"]) * fetch_multiplier), 500
            )

            results = await self._execute_multi_query_search(
                queries_to_search, params["mode"], fetch_limit, params["category"]
            )
            results = await self._apply_all_search_filters(
                results, params, tag_filtered_ids, processed_query, fetch_limit
            )

            duration_ms = int((time.time() - start_time) * 1000)
            return self._finalize_search_response(
                results, params, processed_query, len(queries_to_search), duration_ms
            )

        except Exception as e:
            logger.error("Enhanced search v2 failed: %s", e)
            import traceback

            logger.error(traceback.format_exc())
            return {"success": False, "results": [], "total_count": 0, "error": str(e)}

    def _expand_query_terms(self, query: str, enable_expansion: bool) -> List[str]:
        """Expand query with synonyms and related terms."""
        return self._query_processor.expand_query_terms(query, enable_expansion)

    def _apply_advanced_search_filters(
        self,
        results: List[Dict[str, Any]],
        created_after: Optional[str],
        created_before: Optional[str],
        exclude_terms: Optional[List[str]],
        require_terms: Optional[List[str]],
        exclude_sources: Optional[List[str]],
        verified_only: bool,
        min_score: float,
        fetch_limit: int,
    ) -> List[Dict[str, Any]]:
        """Apply advanced filters to search results."""
        if not any(
            [
                created_after,
                created_before,
                exclude_terms,
                require_terms,
                exclude_sources,
                verified_only,
            ]
        ):
            return results

        from datetime import datetime as dt

        from knowledge.search_quality import AdvancedFilter, SearchFilters

        filters = SearchFilters(
            created_after=dt.fromisoformat(created_after) if created_after else None,
            created_before=dt.fromisoformat(created_before) if created_before else None,
            exclude_terms=exclude_terms,
            require_terms=require_terms,
            exclude_sources=exclude_sources,
            verified_only=verified_only,
            min_score=min_score,
            max_results=fetch_limit,
        )
        advanced_filter = AdvancedFilter(filters)
        return advanced_filter.apply_filters(results)

    def _apply_relevance_scoring(
        self,
        results: List[Dict[str, Any]],
        query: str,
        enable_scoring: bool,
    ) -> List[Dict[str, Any]]:
        """Apply relevance scoring to search results."""
        if not enable_scoring or not results:
            return results

        from knowledge.search_quality import get_relevance_scorer

        scorer = get_relevance_scorer()
        for result in results:
            original_score = result.get("score", 0)
            result["original_score"] = original_score
            result["score"] = scorer.calculate_relevance_score(
                original_score, query, result
            )
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results

    def _track_search_analytics(
        self,
        query: str,
        result_count: int,
        duration_ms: int,
        session_id: Optional[str],
        mode: str,
        tags: Optional[List[str]],
        category: Optional[str],
        query_expansion: bool,
        relevance_scoring: bool,
        track_analytics: bool,
    ) -> None:
        """Track search analytics."""
        get_analytics().track_analytics(
            query,
            result_count,
            duration_ms,
            session_id,
            mode,
            tags,
            category,
            query_expansion,
            relevance_scoring,
            track_analytics,
        )

    def _track_search_analytics_ctx(self, ctx) -> None:
        """Track search analytics using context."""
        get_analytics().track_analytics_ctx(ctx)

    def _cluster_search_results(
        self,
        results: List[Dict[str, Any]],
        enable_clustering: bool,
        offset: int,
        limit: int,
    ) -> tuple:
        """Cluster search results by topic."""
        return self._response_builder.cluster_search_results(
            results, enable_clustering, offset, limit
        )

    def _build_enhanced_search_response(
        self,
        results: List[Dict[str, Any]],
        unclustered: List[Dict[str, Any]],
        clusters,
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
        """Build the enhanced search response."""
        return self._response_builder.build_enhanced_response(
            results,
            unclustered,
            clusters,
            query,
            mode,
            tags,
            min_score,
            enable_reranking,
            enable_query_expansion,
            enable_relevance_scoring,
            enable_clustering,
            queries_count,
            duration_ms,
            offset,
            limit,
        )

    def _build_enhanced_search_response_ctx(self, ctx) -> Dict[str, Any]:
        """Build the enhanced search response using context."""
        return self._response_builder.build_enhanced_response_ctx(ctx)

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
