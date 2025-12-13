# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Search Module

Contains the SearchMixin class for all search-related functionality including
semantic search, keyword search, hybrid search, and query preprocessing.
"""

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from backend.models.task_context import (
    EnhancedSearchContext,
    SearchAnalyticsContext,
    SearchResponseContext,
)
from src.utils.error_boundaries import error_boundary

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


def _decode_redis_hash(fact_data: Dict) -> Dict[str, str]:
    """Decode Redis hash bytes to strings (Issue #315)."""
    decoded = {}
    for k, v in fact_data.items():
        dk = k.decode("utf-8") if isinstance(k, bytes) else k
        dv = v.decode("utf-8") if isinstance(v, bytes) else v
        decoded[dk] = dv
    return decoded


def _matches_category(decoded: Dict[str, str], category: Optional[str]) -> bool:
    """Check if fact matches category filter (Issue #315)."""
    if not category:
        return True
    try:
        metadata = json.loads(decoded.get("metadata", "{}"))
        return metadata.get("category") == category
    except json.JSONDecodeError:
        return False


def _score_fact_by_terms(decoded: Dict[str, str], query_terms: Set[str]) -> float:
    """Calculate term match score for a fact (Issue #315)."""
    content = decoded.get("content", "").lower()
    matches = sum(1 for term in query_terms if term in content)
    return matches / len(query_terms) if matches > 0 else 0


def _build_search_result(decoded: Dict[str, str], key: bytes, score: float) -> Dict[str, Any]:
    """Build search result dict from decoded fact (Issue #315)."""
    fact_id = (
        key.decode("utf-8").replace("fact:", "")
        if isinstance(key, bytes)
        else key.replace("fact:", "")
    )
    try:
        metadata = json.loads(decoded.get("metadata", "{}"))
    except json.JSONDecodeError:
        metadata = {}

    return {
        "content": decoded.get("content", ""),
        "score": score,
        "metadata": {**metadata, "fact_id": fact_id},
        "node_id": fact_id,
        "doc_id": fact_id,
    }


class SearchMixin:
    """
    Search functionality mixin for knowledge base.

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

    async def search(
        self,
        query: str,
        top_k: int = 10,
        similarity_top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        mode: str = "auto",
    ) -> List[Dict[str, Any]]:
        """
        Search the knowledge base with multiple search modes.

        Issue #281: Refactored from 147 lines to use extracted helper methods.

        Args:
            query: Search query
            top_k: Number of results to return (alias for similarity_top_k)
            similarity_top_k: Number of results to return (takes precedence over top_k)
            filters: Optional filters to apply
            mode: Search mode ("vector" for semantic, "text" for keyword, "auto" for hybrid)

        Returns:
            List of search results with content and metadata
        """
        self.ensure_initialized()

        # Handle parameter aliases
        if similarity_top_k is None:
            similarity_top_k = top_k

        if not query.strip():
            return []

        if not self.vector_store:
            logger.warning("Vector store not available for search")
            return []

        try:
            # Step 1: Get query embedding (with caching)
            query_embedding = await self._get_query_embedding(query)

            # Step 2: Query ChromaDB
            results_data = await self._query_chromadb(query_embedding, similarity_top_k)

            # Step 3: Deduplicate and format results
            results = self._deduplicate_results(results_data, similarity_top_k)

            logger.info(
                f"ChromaDB direct search returned {len(results)} unique documents "
                f"(deduplicated) for query: {query[:50]}..."
            )
            return results

        except Exception as e:
            logger.error(f"Knowledge base search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for query, using cache when available. Issue #281: Extracted helper."""
        from llama_index.core import Settings
        from src.knowledge.embedding_cache import get_embedding_cache

        _embedding_cache = get_embedding_cache()
        query_embedding = await _embedding_cache.get(query)

        if query_embedding is None:
            # Cache miss - compute embedding
            query_embedding = await asyncio.to_thread(
                Settings.embed_model.get_text_embedding, query
            )
            await _embedding_cache.put(query, query_embedding)

        return query_embedding

    async def _query_chromadb(
        self, query_embedding: List[float], similarity_top_k: int
    ) -> Dict[str, Any]:
        """Query ChromaDB directly with embedding. Issue #281: Extracted helper."""
        chroma_collection = self.vector_store._collection
        return await asyncio.to_thread(
            chroma_collection.query,
            query_embeddings=[query_embedding],
            n_results=similarity_top_k,
            include=["documents", "metadatas", "distances"],
        )

    def _deduplicate_results(
        self, results_data: Dict[str, Any], similarity_top_k: int
    ) -> List[Dict[str, Any]]:
        """Deduplicate and format ChromaDB results. Issue #281: Extracted helper."""
        seen_documents: Dict[str, Dict[str, Any]] = {}

        if not (results_data and "documents" in results_data and results_data["documents"][0]):
            return []

        for i, doc in enumerate(results_data["documents"][0]):
            score = self._calculate_similarity_score(results_data, i)
            metadata = results_data["metadatas"][0][i] if "metadatas" in results_data else {}
            doc_key = self._get_document_key(metadata, i)

            if doc_key not in seen_documents or score > seen_documents[doc_key]["score"]:
                seen_documents[doc_key] = self._build_result_dict(
                    doc, score, metadata, results_data, i
                )

        results = sorted(seen_documents.values(), key=lambda x: x["score"], reverse=True)
        return results[:similarity_top_k]

    def _calculate_similarity_score(self, results_data: Dict[str, Any], index: int) -> float:
        """Convert distance to similarity score. Issue #281: Extracted helper."""
        distance = results_data["distances"][0][index] if "distances" in results_data else 1.0
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
        self, doc: str, score: float, metadata: Dict[str, Any],
        results_data: Dict[str, Any], index: int
    ) -> Dict[str, Any]:
        """Build result dictionary for a search result. Issue #281: Extracted helper."""
        node_id = results_data["ids"][0][index] if "ids" in results_data else f"result_{index}"
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
        return {"success": False, "results": [], "total_count": 0, "message": "Empty query"}

    def _build_no_tags_match_response(self, processed_query: str) -> Dict[str, Any]:
        """Build response when no facts match tags. Issue #281: Extracted helper."""
        return {
            "success": True, "results": [], "total_count": 0,
            "query_processed": processed_query, "message": "No facts match the specified tags"
        }

    async def _get_tag_filtered_ids(
        self, tags: Optional[List[str]], tags_match_any: bool, processed_query: str
    ) -> tuple:
        """Get tag-filtered fact IDs. Returns (filtered_ids, early_return_response or None)."""
        if not tags:
            return None, None

        tag_result = await self._get_fact_ids_by_tags(tags, match_all=not tags_match_any)
        if tag_result["success"]:
            tag_filtered_ids = tag_result["fact_ids"]
            if not tag_filtered_ids:
                return None, self._build_no_tags_match_response(processed_query)
            return tag_filtered_ids, None
        return None, None

    async def _execute_search_by_mode(
        self, mode: str, processed_query: str, fetch_limit: int, category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Execute search based on mode. Issue #281: Extracted helper."""
        if mode == "keyword":
            return await self._keyword_search(processed_query, fetch_limit, category)
        elif mode == "semantic":
            return await self.search(
                processed_query, top_k=fetch_limit,
                filters={"category": category} if category else None, mode="vector"
            )
        else:  # hybrid mode
            return await self._hybrid_search(processed_query, fetch_limit, category)

    def _apply_post_search_filters(
        self, results: List[Dict[str, Any]], tag_filtered_ids: Optional[Set[str]], min_score: float
    ) -> List[Dict[str, Any]]:
        """Apply tag and score filtering to results. Issue #281: Extracted helper."""
        if tag_filtered_ids is not None:
            results = [r for r in results if r.get("metadata", {}).get("fact_id") in tag_filtered_ids]
        if min_score > 0:
            results = [r for r in results if r.get("score", 0) >= min_score]
        return results

    def _build_success_response(
        self, results: List[Dict[str, Any]], total_count: int, offset: int, limit: int,
        processed_query: str, mode: str, tags: Optional[List[str]], min_score: float, enable_reranking: bool
    ) -> Dict[str, Any]:
        """Build successful search response. Issue #281: Extracted helper."""
        return {
            "success": True, "results": results[offset:offset + limit], "total_count": total_count,
            "query_processed": processed_query, "mode": mode, "tags_applied": tags if tags else [],
            "min_score_applied": min_score, "reranking_applied": enable_reranking,
        }

    @error_boundary(component="knowledge_base", function="enhanced_search")
    async def enhanced_search(
        self, query: str, limit: int = 10, offset: int = 0, category: Optional[str] = None,
        tags: Optional[List[str]] = None, tags_match_any: bool = False, mode: str = "hybrid",
        enable_reranking: bool = False, min_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Enhanced search with tag filtering, hybrid mode, and query preprocessing (Issue #281 refactor)."""
        self.ensure_initialized()

        if not query.strip():
            return self._build_empty_query_response()

        try:
            processed_query = self._preprocess_query(query)

            tag_filtered_ids, early_return = await self._get_tag_filtered_ids(tags, tags_match_any, processed_query)
            if early_return:
                return early_return

            fetch_multiplier = 3 if tags or min_score > 0 else 1.5
            fetch_limit = min(int((limit + offset) * fetch_multiplier), 500)

            results = await self._execute_search_by_mode(mode, processed_query, fetch_limit, category)
            results = self._apply_post_search_filters(results, tag_filtered_ids, min_score)

            if enable_reranking and results:
                results = await self._rerank_results(processed_query, results)

            return self._build_success_response(
                results, len(results), offset, limit, processed_query, mode, tags, min_score, enable_reranking
            )

        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "results": [], "total_count": 0, "error": str(e)}

    def _preprocess_query(self, query: str) -> str:
        """
        Preprocess search query for better results.

        Issue #78: Query preprocessing for search quality.

        Preprocessing steps:
        1. Normalize whitespace
        2. Remove redundant punctuation
        3. Expand common abbreviations
        4. Preserve quoted phrases

        Args:
            query: Raw user query

        Returns:
            Preprocessed query string
        """
        # Normalize whitespace
        processed = " ".join(query.split())

        # Common abbreviations expansion (security/sysadmin context)
        abbreviations = {
            r"\bdir\b": "directory",
            r"\bcmd\b": "command",
            r"\bpwd\b": "password",
            r"\bauth\b": "authentication",
            r"\bperm\b": "permission",
            r"\bperms\b": "permissions",
            r"\bconfig\b": "configuration",
            r"\benv\b": "environment",
            r"\bvar\b": "variable",
            r"\bvars\b": "variables",
            r"\bproc\b": "process",
            r"\bsvc\b": "service",
            r"\bpkg\b": "package",
            r"\brepo\b": "repository",
            r"\binfo\b": "information",
            r"\bdoc\b": "documentation",
            r"\bdocs\b": "documentation",
        }

        # Only expand if not in quotes
        if '"' not in processed and "'" not in processed:
            for abbr, expansion in abbreviations.items():
                processed = re.sub(abbr, expansion, processed, flags=re.IGNORECASE)

        return processed.strip()

    def _decode_tag_results(self, tag_results: list) -> List[Set[str]]:
        """Decode tag results from Redis to sets of fact IDs. Issue #281: Extracted helper."""
        tag_fact_sets = []
        for fact_ids in tag_results:
            if fact_ids:
                decoded_ids = {fid.decode("utf-8") if isinstance(fid, bytes) else fid for fid in fact_ids}
                tag_fact_sets.append(decoded_ids)
            else:
                tag_fact_sets.append(set())
        return tag_fact_sets

    def _combine_tag_fact_sets(self, tag_fact_sets: List[Set[str]], match_all: bool) -> Set[str]:
        """Combine fact sets based on match_all flag. Issue #281: Extracted helper."""
        if not tag_fact_sets:
            return set()
        if match_all:
            result_ids = tag_fact_sets[0]
            for fact_set in tag_fact_sets[1:]:
                result_ids = result_ids.intersection(fact_set)
        else:
            result_ids = set()
            for fact_set in tag_fact_sets:
                result_ids = result_ids.union(fact_set)
        return result_ids

    async def _get_fact_ids_by_tags(self, tags: List[str], match_all: bool = True) -> Dict[str, Any]:
        """Get fact IDs matching specified tags (Issue #281 refactor)."""
        try:
            if not self.aioredis_client:
                return {"success": False, "fact_ids": set(), "message": "Redis not initialized"}

            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {"success": False, "fact_ids": set(), "message": "No valid tags"}

            pipeline = self.aioredis_client.pipeline()
            for tag in normalized_tags:
                pipeline.smembers(f"tag:{tag}")
            tag_results = await pipeline.execute()

            tag_fact_sets = self._decode_tag_results(tag_results)
            result_ids = self._combine_tag_fact_sets(tag_fact_sets, match_all)

            return {"success": True, "fact_ids": result_ids}

        except Exception as e:
            logger.error(f"Failed to get fact IDs by tags: {e}")
            return {"success": False, "fact_ids": set(), "error": str(e)}

    async def _process_keyword_batch(
        self, keys: list, query_terms: Set[str], category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Process a batch of Redis keys for keyword search. Issue #281: Extracted helper."""
        results = []
        pipeline = self.aioredis_client.pipeline()
        for key in keys:
            pipeline.hgetall(key)
        facts_data = await pipeline.execute()

        for key, fact_data in zip(keys, facts_data):
            if not fact_data:
                continue
            decoded = _decode_redis_hash(fact_data)
            if not _matches_category(decoded, category):
                continue
            score = _score_fact_by_terms(decoded, query_terms)
            if score > 0:
                results.append(_build_search_result(decoded, key, score))
        return results

    async def _keyword_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform keyword-based search using Redis (Issue #281 refactor)."""
        try:
            if not self.aioredis_client:
                return []

            query_terms = set(query.lower().split())
            if not query_terms:
                return []

            results, cursor, scanned, max_scan = [], b"0", 0, 10000

            while scanned < max_scan:
                cursor, keys = await self.aioredis_client.scan(cursor=cursor, match="fact:*", count=100)
                scanned += len(keys)

                if keys:
                    batch_results = await self._process_keyword_batch(keys, query_terms, category)
                    results.extend(batch_results)

                if cursor == b"0":
                    break

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    def _process_rrf_results(
        self, results: List[Dict[str, Any]], rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]], k: int, prefix: str
    ) -> None:
        """Process results for RRF scoring. Issue #281: Extracted helper."""
        for rank, result in enumerate(results):
            fact_id = result.get("metadata", {}).get("fact_id") or result.get("node_id", f"{prefix}_{rank}")
            rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
            if fact_id not in result_map:
                result_map[fact_id] = result

    def _build_rrf_results(
        self, rrf_scores: Dict[str, float], result_map: Dict[str, Dict[str, Any]], limit: int
    ) -> List[Dict[str, Any]]:
        """Build final RRF-ranked results. Issue #281: Extracted helper."""
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        max_rrf = max(rrf_scores.values()) if rrf_scores else 1
        results = []
        for fact_id in sorted_ids[:limit]:
            result = result_map[fact_id].copy()
            result["score"] = rrf_scores[fact_id] / max_rrf
            result["rrf_score"] = rrf_scores[fact_id]
            results.append(result)
        return results

    async def _hybrid_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search combining semantic and keyword results (Issue #281 refactor)."""
        try:
            semantic_task = asyncio.create_task(
                self.search(query, top_k=limit, filters={"category": category} if category else None, mode="vector")
            )
            keyword_task = asyncio.create_task(self._keyword_search(query, limit, category))
            semantic_results, keyword_results = await asyncio.gather(semantic_task, keyword_task)

            # Reciprocal Rank Fusion with k=60 (standard constant)
            k, rrf_scores, result_map = 60, {}, {}
            self._process_rrf_results(semantic_results, rrf_scores, result_map, k, "sem")
            self._process_rrf_results(keyword_results, rrf_scores, result_map, k, "kw")

            return self._build_rrf_results(rrf_scores, result_map, limit)

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to semantic search
            return await self.search(query, top_k=limit, mode="vector")

    async def _ensure_cross_encoder(self):
        """Ensure cross-encoder model is loaded. Issue #281: Extracted helper."""
        from sentence_transformers import CrossEncoder

        if not hasattr(self, "_cross_encoder") or self._cross_encoder is None:
            self._cross_encoder = await asyncio.to_thread(CrossEncoder, "cross-encoder/ms-marco-MiniLM-L-6-v2")
        return self._cross_encoder

    def _apply_rerank_scores(self, results: List[Dict[str, Any]], scores: list) -> None:
        """Apply rerank scores to results. Issue #281: Extracted helper."""
        for i, result in enumerate(results):
            result["rerank_score"] = float(scores[i])
        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        for result in results:
            result["original_score"] = result.get("score", 0)
            result["score"] = result.get("rerank_score", 0)

    async def _rerank_results(
        self, query: str, results: List[Dict[str, Any]], top_k: int = None
    ) -> List[Dict[str, Any]]:
        """Rerank results using cross-encoder for improved relevance (Issue #281 refactor)."""
        try:
            try:
                from sentence_transformers import CrossEncoder  # noqa: F401
            except ImportError:
                logger.warning("CrossEncoder not available, skipping reranking")
                return results

            if not results:
                return results

            cross_encoder = await self._ensure_cross_encoder()
            pairs = [(query, r.get("content", "")) for r in results]
            scores = await asyncio.to_thread(cross_encoder.predict, pairs)
            self._apply_rerank_scores(results, scores)

            return results[:top_k] if top_k else results

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results

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
        # Issue #78: New parameters for search quality improvements
        enable_query_expansion: bool = False,
        enable_relevance_scoring: bool = False,
        enable_clustering: bool = False,
        track_analytics: bool = True,
        created_after: Optional[str] = None,  # ISO format datetime
        created_before: Optional[str] = None,
        exclude_terms: Optional[List[str]] = None,
        require_terms: Optional[List[str]] = None,
        exclude_sources: Optional[List[str]] = None,
        verified_only: bool = False,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced search v2 with full Issue #78 improvements.

        Issue #375: This method now delegates to enhanced_search_v2_ctx using
        EnhancedSearchContext dataclass. The original signature is preserved
        for backward compatibility.

        Issue #78: Search quality improvements including:
        - Query expansion with synonyms and related terms
        - Relevance scoring with recency, popularity, authority
        - Advanced filtering (date ranges, exclusions)
        - Result clustering by topic
        - Search analytics tracking

        Args:
            query: Search query string
            limit: Maximum results to return (default: 10)
            offset: Pagination offset (default: 0)
            category: Optional category filter
            tags: Optional list of tags to filter by
            tags_match_any: If True, match ANY tag; False matches ALL
            mode: Search mode ("semantic", "keyword", "hybrid")
            enable_reranking: Enable cross-encoder reranking
            min_score: Minimum similarity score threshold (0.0-1.0)
            enable_query_expansion: Expand query with synonyms (Issue #78)
            enable_relevance_scoring: Apply relevance boosting (Issue #78)
            enable_clustering: Cluster results by topic (Issue #78)
            track_analytics: Track search analytics (Issue #78)
            created_after: Filter by creation date (ISO format)
            created_before: Filter by creation date (ISO format)
            exclude_terms: Terms to exclude from results
            require_terms: Terms that must be present
            exclude_sources: Sources to exclude
            verified_only: Only return verified results
            session_id: Session ID for analytics tracking

        Returns:
            Enhanced search response with optional clustering
        """
        # Issue #375: Create context from parameters and delegate
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

    @error_boundary(component="knowledge_base", function="enhanced_search_v2_ctx")
    async def enhanced_search_v2_ctx(
        self,
        ctx: EnhancedSearchContext,
    ) -> Dict[str, Any]:
        """
        Enhanced search v2 using EnhancedSearchContext.

        Issue #375: Refactored from 20-parameter signature to accept a single
        context object. This is the primary implementation; enhanced_search_v2
        now delegates to this method for backward compatibility.

        Args:
            ctx: EnhancedSearchContext containing all search parameters grouped
                 into query_params, filters, and options dataclasses.

        Returns:
            Enhanced search response with optional clustering
        """
        import time

        self.ensure_initialized()

        # Extract commonly used values for readability
        query = ctx.query_params.query
        limit = ctx.query_params.limit
        offset = ctx.query_params.offset
        tags = ctx.query_params.tags
        tags_match_any = ctx.query_params.tags_match_any
        exclude_terms = ctx.query_params.exclude_terms
        require_terms = ctx.query_params.require_terms

        category = ctx.filters.category
        created_after = ctx.filters.created_after
        created_before = ctx.filters.created_before
        exclude_sources = ctx.filters.exclude_sources
        verified_only = ctx.filters.verified_only

        mode = ctx.options.mode
        enable_reranking = ctx.options.enable_reranking
        min_score = ctx.options.min_score
        enable_query_expansion = ctx.options.enable_query_expansion
        enable_relevance_scoring = ctx.options.enable_relevance_scoring
        enable_clustering = ctx.options.enable_clustering
        track_analytics = ctx.options.track_analytics

        session_id = ctx.session_id

        if not query.strip():
            return self._build_empty_query_response()

        start_time = time.time()

        try:
            processed_query = self._preprocess_query(query)

            # Issue #281: Use extracted helper for query expansion
            queries_to_search = self._expand_query_terms(
                processed_query, enable_query_expansion
            )

            # Get tag-filtered IDs if needed
            tag_filtered_ids, early_return = await self._get_tag_filtered_ids(
                tags, tags_match_any, processed_query
            )
            if early_return:
                return early_return

            # Calculate fetch limit with multiplier for filtering
            fetch_multiplier = 3 if (tags or min_score > 0 or exclude_terms) else 1.5
            fetch_limit = min(int((limit + offset) * fetch_multiplier), 500)

            # Execute search with all query variations
            all_results = []
            seen_ids: Set[str] = set()

            for search_query in queries_to_search:
                query_results = await self._execute_search_by_mode(
                    mode, search_query, fetch_limit, category
                )
                for result in query_results:
                    result_id = result.get("metadata", {}).get("fact_id") or result.get("node_id", "")
                    if result_id not in seen_ids:
                        seen_ids.add(result_id)
                        result["matched_query"] = search_query  # Track which query matched
                        all_results.append(result)

            # Apply tag and score filters
            results = self._apply_post_search_filters(all_results, tag_filtered_ids, min_score)

            # Issue #281: Use extracted helper for advanced filtering
            results = self._apply_advanced_search_filters(
                results, created_after, created_before, exclude_terms,
                require_terms, exclude_sources, verified_only, min_score, fetch_limit
            )

            # Issue #281: Use extracted helper for relevance scoring
            results = self._apply_relevance_scoring(
                results, processed_query, enable_relevance_scoring
            )

            # Reranking with cross-encoder
            if enable_reranking and results:
                results = await self._rerank_results(processed_query, results)

            # Calculate search duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Issue #281: Use extracted helper for analytics tracking
            self._track_search_analytics(
                query, len(results), duration_ms, session_id, mode,
                tags, category, enable_query_expansion, enable_relevance_scoring,
                track_analytics
            )

            # Issue #281: Use extracted helpers for clustering and response
            clusters, unclustered = self._cluster_search_results(
                results, enable_clustering, offset, limit
            )

            return self._build_enhanced_search_response(
                results, unclustered, clusters, processed_query, mode,
                tags, min_score, enable_reranking, enable_query_expansion,
                enable_relevance_scoring, enable_clustering,
                len(queries_to_search), duration_ms, offset, limit
            )

        except Exception as e:
            logger.error(f"Enhanced search v2 failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "results": [], "total_count": 0, "error": str(e)}

    def _expand_query_terms(self, query: str, enable_expansion: bool) -> List[str]:
        """
        Expand query with synonyms and related terms.

        Issue #281: Extracted from enhanced_search_v2 for clarity.

        Args:
            query: Processed query string
            enable_expansion: Whether to enable query expansion

        Returns:
            List of query variations to search
        """
        if not enable_expansion:
            return [query]

        from src.knowledge.search_quality import get_query_expander

        expander = get_query_expander()
        queries = expander.expand_query(query)
        logger.debug(f"Query expansion: {len(queries)} variations")
        return queries

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
        """
        Apply advanced filters to search results.

        Issue #281: Extracted from enhanced_search_v2 for clarity.

        Args:
            results: Initial search results
            created_after: Filter by creation date (ISO format)
            created_before: Filter by creation date (ISO format)
            exclude_terms: Terms to exclude
            require_terms: Required terms
            exclude_sources: Sources to exclude
            verified_only: Only verified results
            min_score: Minimum score threshold
            fetch_limit: Maximum results limit

        Returns:
            Filtered results list
        """
        if not any([created_after, created_before, exclude_terms,
                    require_terms, exclude_sources, verified_only]):
            return results

        from datetime import datetime as dt
        from src.knowledge.search_quality import SearchFilters, AdvancedFilter

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
        """
        Apply relevance scoring to search results.

        Issue #281: Extracted from enhanced_search_v2 for clarity.

        Args:
            results: Search results to score
            query: Processed query for scoring
            enable_scoring: Whether to enable relevance scoring

        Returns:
            Scored and re-sorted results
        """
        if not enable_scoring or not results:
            return results

        from src.knowledge.search_quality import get_relevance_scorer

        scorer = get_relevance_scorer()
        for result in results:
            original_score = result.get("score", 0)
            result["original_score"] = original_score
            result["score"] = scorer.calculate_relevance_score(
                original_score, query, result
            )
        # Re-sort by new scores
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
        """
        Track search analytics.

        Issue #281: Extracted from enhanced_search_v2 for clarity.
        Issue #375: Delegates to _track_search_analytics_ctx using
        SearchAnalyticsContext for backward compatibility.

        Args:
            query: Original query
            result_count: Number of results found
            duration_ms: Search duration in milliseconds
            session_id: Session ID for tracking
            mode: Search mode used
            tags: Tags applied
            category: Category filter applied
            query_expansion: Whether query expansion was enabled
            relevance_scoring: Whether relevance scoring was enabled
            track_analytics: Whether to track analytics
        """
        # Issue #375: Create context and delegate
        ctx = SearchAnalyticsContext(
            query=query,
            result_count=result_count,
            duration_ms=duration_ms,
            session_id=session_id,
            mode=mode,
            tags=tags,
            category=category,
            query_expansion=query_expansion,
            relevance_scoring=relevance_scoring,
            track_analytics=track_analytics,
        )
        self._track_search_analytics_ctx(ctx)

    def _track_search_analytics_ctx(
        self,
        ctx: SearchAnalyticsContext,
    ) -> None:
        """
        Track search analytics using context.

        Issue #375: Refactored from 10-parameter signature to accept a single
        SearchAnalyticsContext object.

        Args:
            ctx: SearchAnalyticsContext containing all analytics parameters.
        """
        if not ctx.track_analytics:
            return

        from src.knowledge.search_quality import get_search_analytics

        analytics = get_search_analytics()
        analytics.record_search(
            query=ctx.query,
            result_count=ctx.result_count,
            duration_ms=ctx.duration_ms,
            session_id=ctx.session_id,
            filters={
                "mode": ctx.mode,
                "tags": ctx.tags,
                "category": ctx.category,
                "query_expansion": ctx.query_expansion,
                "relevance_scoring": ctx.relevance_scoring,
            },
        )

    def _cluster_search_results(
        self,
        results: List[Dict[str, Any]],
        enable_clustering: bool,
        offset: int,
        limit: int,
    ) -> tuple:
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
                "results": c.results[offset:offset + limit],
            }
            for c in cluster_objects
        ]
        return clusters, unclustered

    def _build_enhanced_search_response(
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
        Issue #375: Delegates to _build_enhanced_search_response_ctx using
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
        return self._build_enhanced_search_response_ctx(ctx)

    def _build_enhanced_search_response_ctx(
        self,
        ctx: SearchResponseContext,
    ) -> Dict[str, Any]:
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
            ctx.unclustered[ctx.offset:ctx.offset + ctx.limit]
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

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
