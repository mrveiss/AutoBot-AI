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
        """Search the knowledge base with multiple search modes.

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
            # Import here to avoid circular dependency
            from llama_index.core import Settings

            from src.knowledge.embedding_cache import get_embedding_cache

            _embedding_cache = get_embedding_cache()

            # Use direct ChromaDB queries to avoid VectorStoreIndex blocking with 545K vectors
            chroma_collection = self.vector_store._collection

            # Generate embedding for query using the same model
            # P0 OPTIMIZATION: Use embedding cache to avoid regenerating identical queries
            # Check cache first
            query_embedding = await _embedding_cache.get(query)

            if query_embedding is None:
                # Cache miss - compute embedding
                query_embedding = await asyncio.to_thread(
                    Settings.embed_model.get_text_embedding, query
                )
                # Store in cache for future use
                await _embedding_cache.put(query, query_embedding)
            # else: Cache hit - embedding already loaded

            # Query ChromaDB directly (avoids index creation overhead)
            # Note: IDs are always returned by default, don't include in 'include' parameter
            results_data = await asyncio.to_thread(
                chroma_collection.query,
                query_embeddings=[query_embedding],
                n_results=similarity_top_k,
                include=["documents", "metadatas", "distances"],
            )

            # Format results
            results = []
            seen_documents = (
                {}
            )  # Track unique documents by metadata to prevent duplicates

            if (
                results_data
                and "documents" in results_data
                and results_data["documents"][0]
            ):
                for i, doc in enumerate(results_data["documents"][0]):
                    # Convert distance to similarity score (cosine: 0=identical, 2=opposite)
                    distance = (
                        results_data["distances"][0][i]
                        if "distances" in results_data
                        else 1.0
                    )
                    score = max(
                        0.0, 1.0 - (distance / 2.0)
                    )  # Convert to 0-1 similarity

                    metadata = (
                        results_data["metadatas"][0][i]
                        if "metadatas" in results_data
                        else {}
                    )

                    # Create unique document key to deduplicate chunks from same source
                    # Use fact_id first (most reliable), fallback to title+category
                    doc_key = metadata.get("fact_id")
                    if not doc_key:
                        title = metadata.get("title", "")
                        category = metadata.get("category", "")
                        doc_key = (
                            f"{category}:{title}" if (title or category) else f"doc_{i}"
                        )

                    # Keep only highest-scoring result per unique document
                    if (
                        doc_key not in seen_documents
                        or score > seen_documents[doc_key]["score"]
                    ):
                        result = {
                            "content": doc,
                            "score": score,
                            "metadata": metadata,
                            "node_id": (
                                results_data["ids"][0][i]
                                if "ids" in results_data
                                else f"result_{i}"
                            ),
                            "doc_id": (
                                results_data["ids"][0][i]
                                if "ids" in results_data
                                else f"result_{i}"
                            ),  # V1 compatibility
                        }
                        seen_documents[doc_key] = result

            # Convert to list and sort by score descending
            results = sorted(
                seen_documents.values(), key=lambda x: x["score"], reverse=True
            )

            # Limit to top_k after deduplication
            results = results[:similarity_top_k]

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
        """
        Enhanced search with tag filtering, hybrid mode, and query preprocessing.

        Issue #78: Search Quality Improvements

        Args:
            query: Search query (will be preprocessed)
            limit: Maximum results to return
            offset: Pagination offset
            category: Optional category filter
            tags: Optional list of tags to filter by
            tags_match_any: If True, match ANY tag. If False, match ALL tags.
            mode: Search mode ("semantic", "keyword", "hybrid")
            enable_reranking: Enable cross-encoder reranking for better relevance
            min_score: Minimum similarity score threshold (0.0-1.0)

        Returns:
            Dict with results, total_count, and search metadata
        """
        self.ensure_initialized()

        if not query.strip():
            return {
                "success": False,
                "results": [],
                "total_count": 0,
                "message": "Empty query",
            }

        try:
            # Step 1: Query preprocessing
            processed_query = self._preprocess_query(query)

            # Step 2: Get candidate fact IDs from tags if specified
            tag_filtered_ids: Optional[Set[str]] = None
            if tags:
                tag_result = await self._get_fact_ids_by_tags(
                    tags, match_all=not tags_match_any
                )
                if tag_result["success"]:
                    tag_filtered_ids = tag_result["fact_ids"]
                    if not tag_filtered_ids:
                        # No facts match the tag filter
                        return {
                            "success": True,
                            "results": [],
                            "total_count": 0,
                            "query_processed": processed_query,
                            "message": "No facts match the specified tags",
                        }

            # Step 3: Perform search based on mode
            # Request more results than needed to allow for filtering
            fetch_multiplier = 3 if tags or min_score > 0 else 1.5
            fetch_limit = min(int((limit + offset) * fetch_multiplier), 500)

            if mode == "keyword":
                # Keyword-only search (uses Redis text search if available)
                results = await self._keyword_search(
                    processed_query, fetch_limit, category
                )
            elif mode == "semantic":
                # Semantic-only search (existing ChromaDB search)
                results = await self.search(
                    processed_query,
                    top_k=fetch_limit,
                    filters={"category": category} if category else None,
                    mode="vector",
                )
            else:
                # Hybrid mode: combine semantic and keyword results
                results = await self._hybrid_search(
                    processed_query, fetch_limit, category
                )

            # Step 4: Filter by tags if specified
            if tag_filtered_ids is not None:
                results = [
                    r
                    for r in results
                    if r.get("metadata", {}).get("fact_id") in tag_filtered_ids
                ]

            # Step 5: Apply minimum score threshold
            if min_score > 0:
                results = [r for r in results if r.get("score", 0) >= min_score]

            # Step 6: Optional reranking with cross-encoder
            if enable_reranking and results:
                results = await self._rerank_results(processed_query, results)

            # Step 7: Get total before pagination
            total_count = len(results)

            # Step 8: Apply pagination
            paginated_results = results[offset : offset + limit]

            return {
                "success": True,
                "results": paginated_results,
                "total_count": total_count,
                "query_processed": processed_query,
                "mode": mode,
                "tags_applied": tags if tags else [],
                "min_score_applied": min_score,
                "reranking_applied": enable_reranking,
            }

        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return {
                "success": False,
                "results": [],
                "total_count": 0,
                "error": str(e),
            }

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

    async def _get_fact_ids_by_tags(
        self, tags: List[str], match_all: bool = True
    ) -> Dict[str, Any]:
        """
        Get fact IDs matching specified tags.

        Args:
            tags: List of tags to match
            match_all: If True, facts must have ALL tags

        Returns:
            Dict with success status and set of fact_ids
        """
        try:
            if not self.aioredis_client:
                return {
                    "success": False,
                    "fact_ids": set(),
                    "message": "Redis not initialized",
                }

            # Normalize tags
            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {"success": False, "fact_ids": set(), "message": "No valid tags"}

            # Get fact IDs for each tag using pipeline
            pipeline = self.aioredis_client.pipeline()
            for tag in normalized_tags:
                pipeline.smembers(f"tag:{tag}")
            tag_results = await pipeline.execute()

            # Convert to sets
            tag_fact_sets = []
            for fact_ids in tag_results:
                if fact_ids:
                    decoded_ids = {
                        fid.decode("utf-8") if isinstance(fid, bytes) else fid
                        for fid in fact_ids
                    }
                    tag_fact_sets.append(decoded_ids)
                else:
                    tag_fact_sets.append(set())

            # Calculate matching IDs
            if not tag_fact_sets:
                return {"success": True, "fact_ids": set()}

            if match_all:
                # Intersection - must have ALL tags
                result_ids = tag_fact_sets[0]
                for fact_set in tag_fact_sets[1:]:
                    result_ids = result_ids.intersection(fact_set)
            else:
                # Union - ANY tag matches
                result_ids = set()
                for fact_set in tag_fact_sets:
                    result_ids = result_ids.union(fact_set)

            return {"success": True, "fact_ids": result_ids}

        except Exception as e:
            logger.error(f"Failed to get fact IDs by tags: {e}")
            return {"success": False, "fact_ids": set(), "error": str(e)}

    async def _keyword_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword-based search using Redis.

        Args:
            query: Search query
            limit: Maximum results
            category: Optional category filter

        Returns:
            List of search results
        """
        try:
            if not self.aioredis_client:
                return []

            # Tokenize query
            query_terms = set(query.lower().split())
            if not query_terms:
                return []

            # SCAN through facts and score by term matches
            # This is a simple implementation; could be optimized with Redis Search module
            results = []
            cursor = b"0"
            scanned = 0
            max_scan = 10000  # Safety limit

            while scanned < max_scan:
                cursor, keys = await self.aioredis_client.scan(
                    cursor=cursor, match="fact:*", count=100
                )
                scanned += len(keys)

                if keys:
                    # Batch fetch and process (Issue #315 - reduced nesting)
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

                if cursor == b"0":
                    break

            # Sort by score and limit
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    async def _hybrid_search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword results.

        Uses reciprocal rank fusion (RRF) to combine rankings.

        Args:
            query: Search query
            limit: Maximum results
            category: Optional category filter

        Returns:
            List of merged and re-ranked results
        """
        try:
            # Run both searches in parallel
            semantic_task = asyncio.create_task(
                self.search(
                    query,
                    top_k=limit,
                    filters={"category": category} if category else None,
                    mode="vector",
                )
            )
            keyword_task = asyncio.create_task(
                self._keyword_search(query, limit, category)
            )

            semantic_results, keyword_results = await asyncio.gather(
                semantic_task, keyword_task
            )

            # Reciprocal Rank Fusion (RRF)
            # Score = sum(1 / (k + rank)) across all rankings
            # Using k=60 as standard RRF constant
            k = 60
            rrf_scores: Dict[str, float] = {}
            result_map: Dict[str, Dict[str, Any]] = {}

            # Process semantic results
            for rank, result in enumerate(semantic_results):
                fact_id = result.get("metadata", {}).get("fact_id") or result.get(
                    "node_id", f"sem_{rank}"
                )
                rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
                if fact_id not in result_map:
                    result_map[fact_id] = result

            # Process keyword results
            for rank, result in enumerate(keyword_results):
                fact_id = result.get("metadata", {}).get("fact_id") or result.get(
                    "node_id", f"kw_{rank}"
                )
                rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + (1 / (k + rank + 1))
                if fact_id not in result_map:
                    result_map[fact_id] = result

            # Sort by RRF score
            sorted_ids = sorted(
                rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True
            )

            # Build final results with normalized scores
            max_rrf = max(rrf_scores.values()) if rrf_scores else 1
            results = []
            for fact_id in sorted_ids[:limit]:
                result = result_map[fact_id].copy()
                # Normalize RRF score to 0-1 range
                result["score"] = rrf_scores[fact_id] / max_rrf
                result["rrf_score"] = rrf_scores[fact_id]
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to semantic search
            return await self.search(query, top_k=limit, mode="vector")

    async def _rerank_results(
        self, query: str, results: List[Dict[str, Any]], top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using cross-encoder for improved relevance.

        Args:
            query: Original search query
            results: Initial search results
            top_k: Maximum results to return after reranking

        Returns:
            Reranked results
        """
        try:
            # Check if cross-encoder is available
            try:
                from sentence_transformers import CrossEncoder
            except ImportError:
                logger.warning("CrossEncoder not available, skipping reranking")
                return results

            if not results:
                return results

            # Use cached cross-encoder or create new one
            if not hasattr(self, "_cross_encoder") or self._cross_encoder is None:
                # Use a lightweight cross-encoder model
                self._cross_encoder = await asyncio.to_thread(
                    CrossEncoder, "cross-encoder/ms-marco-MiniLM-L-6-v2"
                )

            # Prepare pairs for scoring
            pairs = [(query, r.get("content", "")) for r in results]

            # Score all pairs
            scores = await asyncio.to_thread(self._cross_encoder.predict, pairs)

            # Attach scores and sort
            for i, result in enumerate(results):
                result["rerank_score"] = float(scores[i])

            results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

            # Update primary score to rerank score
            for result in results:
                result["original_score"] = result.get("score", 0)
                result["score"] = result.get("rerank_score", 0)

            if top_k:
                results = results[:top_k]

            return results

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return results

    def ensure_initialized(self):
        """
        Ensure the knowledge base is initialized.
        This method should be implemented in base class.
        """
        # This will be available from KnowledgeBaseCore when composed
        raise NotImplementedError("Should be implemented in composed class")
